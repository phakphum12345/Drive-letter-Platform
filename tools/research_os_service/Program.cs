using System.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

const string ServiceName = "ResearchOSService";

var host = Host.CreateDefaultBuilder(args)
    .UseWindowsService(options => options.ServiceName = ServiceName)
    .ConfigureServices(services => services.AddHostedService<ResearchOsApiWorker>())
    .Build();

await host.RunAsync();

sealed class ResearchOsApiWorker : BackgroundService
{
    private readonly ILogger<ResearchOsApiWorker> _logger;
    private readonly SemaphoreSlim _processStopLock = new(1, 1);
    private Process? _process;

    public ResearchOsApiWorker(ILogger<ResearchOsApiWorker> logger)
    {
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var repoRoot = ResolveRepoRoot();
        var dataDir = Environment.GetEnvironmentVariable("RESEARCH_OS_DATA_DIR")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ResearchOS");
        var pythonExe = ResolvePython(repoRoot);
        var apiDir = Path.Combine(repoRoot, "tools", "research_os_api");
        var serverPath = Path.Combine(apiDir, "server.py");

        if (!File.Exists(serverPath))
        {
            throw new FileNotFoundException("Research OS API entrypoint not found", serverPath);
        }

        Directory.CreateDirectory(dataDir);
        Directory.CreateDirectory(Path.Combine(dataDir, "sessions"));
        Directory.CreateDirectory(Path.Combine(dataDir, "database"));
        Directory.CreateDirectory(Path.Combine(dataDir, "artifacts"));
        Directory.CreateDirectory(Path.Combine(dataDir, "logs"));

        var stdoutPath = Path.Combine(dataDir, "logs", "service-api.out.log");
        var stderrPath = Path.Combine(dataDir, "logs", "service-api.err.log");

        // Do not hash the full distribution manifest before every API startup.
        // Recovery is deferred until the child exits unexpectedly, so a full
        // integrity scan cannot consume the health-check startup budget.

        _logger.LogInformation("Research OS root: {RepoRoot}", repoRoot);
        _logger.LogInformation("Research OS Python: {PythonExe}", pythonExe);
        _logger.LogInformation("Research OS data: {DataDir}", dataDir);

        var startInfo = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = Quote(serverPath),
            WorkingDirectory = apiDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        startInfo.Environment["RESEARCH_OS_DATA_DIR"] = dataDir;
        startInfo.Environment["RESEARCH_OS_CONVERSATION_STORE"] = Path.Combine(dataDir, "sessions", "conversations.json");
        startInfo.Environment["RESEARCH_OS_API_HOST"] = Environment.GetEnvironmentVariable("RESEARCH_OS_API_HOST") ?? "127.0.0.1";
        startInfo.Environment["RESEARCH_OS_API_PORT"] = Environment.GetEnvironmentVariable("RESEARCH_OS_API_PORT") ?? "8787";
        startInfo.Environment["HOST"] = startInfo.Environment["RESEARCH_OS_API_HOST"]!;
        startInfo.Environment["PORT"] = startInfo.Environment["RESEARCH_OS_API_PORT"]!;

        foreach (var variable in new[]
        {
            "RESEARCH_OS_GOOGLE_CLIENT_ID",
            "RESEARCH_OS_GOOGLE_CLIENT_SECRET",
            "RESEARCH_OS_GOOGLE_REDIRECT_URI",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
        })
        {
            var value = Environment.GetEnvironmentVariable(variable);
            if (!string.IsNullOrWhiteSpace(value))
            {
                startInfo.Environment[variable] = value;
            }
        }

        _process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!_process.Start())
        {
            throw new InvalidOperationException("Failed to start Research OS API process.");
        }

        _logger.LogInformation("Research OS API started with PID {Pid}", _process.Id);

        var stdoutTask = PumpAsync(_process.StandardOutput, stdoutPath, stoppingToken);
        var stderrTask = PumpAsync(_process.StandardError, stderrPath, stoppingToken);
        var exitTask = _process.WaitForExitAsync(stoppingToken);

        try
        {
            await exitTask;
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            await StopChildProcessAsync(CancellationToken.None);
            return;
        }
        finally
        {
            if (stoppingToken.IsCancellationRequested)
            {
                await StopChildProcessAsync(CancellationToken.None);
            }

            await Task.WhenAll(IgnoreCancellation(stdoutTask), IgnoreCancellation(stderrTask));
        }

        if (!stoppingToken.IsCancellationRequested)
        {
            // The child has exited, so the recovery helper can safely inspect and
            // replace manifest-listed files without racing a live API process.
            // A successful repair is followed by the existing SCM service restart.
            RunRuntimeRecovery(repoRoot, dataDir, _logger);
            throw new InvalidOperationException($"Research OS API exited unexpectedly with code {_process?.ExitCode}; Runtime recovery was attempted.");
        }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        await StopChildProcessAsync(cancellationToken);
        await base.StopAsync(cancellationToken);
        await StopChildProcessAsync(CancellationToken.None);
    }

    public override void Dispose()
    {
        try
        {
            StopChildProcessAsync(CancellationToken.None).GetAwaiter().GetResult();
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to terminate Research OS API during worker disposal");
        }
        finally
        {
            _processStopLock.Dispose();
            base.Dispose();
        }
    }

    private async Task StopChildProcessAsync(CancellationToken cancellationToken)
    {
        await _processStopLock.WaitAsync(cancellationToken);
        try
        {
            var process = _process;
            if (process is null)
            {
                return;
            }

            try
            {
                if (!process.HasExited)
                {
                    _logger.LogInformation("Stopping Research OS API PID {Pid} and its process tree", process.Id);
                    process.Kill(entireProcessTree: true);

                    using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                    timeout.CancelAfter(TimeSpan.FromSeconds(10));
                    await process.WaitForExitAsync(timeout.Token);
                }
            }
            catch (OperationCanceledException)
            {
                _logger.LogWarning("Timed out waiting for Research OS API PID {Pid} to exit", SafePid(process));
                try { process.Kill(entireProcessTree: true); } catch { }
            }
            catch (InvalidOperationException)
            {
                // The process already exited between HasExited and Kill/WaitForExitAsync.
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to stop Research OS API child process cleanly");
                try { process.Kill(entireProcessTree: true); } catch { }
            }
            finally
            {
                try { process.Dispose(); } catch { }
                if (ReferenceEquals(_process, process))
                {
                    _process = null;
                }
            }
        }
        finally
        {
            _processStopLock.Release();
        }
    }

    private static void RunRuntimeRecovery(string repoRoot, string dataDir, ILogger logger)
    {
        var recoveryScript = Path.Combine(repoRoot, "tools", "recover-research-os-runtime.ps1");
        if (!File.Exists(recoveryScript))
        {
            logger.LogWarning("Runtime recovery helper is missing; automatic integrity repair is unavailable: {Path}", recoveryScript);
            return;
        }

        var systemDirectory = Environment.GetFolderPath(Environment.SpecialFolder.System);
        var powershell = Path.Combine(systemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(powershell))
        {
            throw new FileNotFoundException("Runtime recovery requires Windows PowerShell.", powershell);
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = powershell,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in new[]
        {
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", recoveryScript, "-InstallRoot", repoRoot, "-DataDir", dataDir
        })
        {
            startInfo.ArgumentList.Add(argument);
        }

        using var recovery = new Process { StartInfo = startInfo };
        if (!recovery.Start())
        {
            throw new InvalidOperationException("Failed to start the Runtime recovery helper.");
        }

        var stdout = recovery.StandardOutput.ReadToEndAsync();
        var stderr = recovery.StandardError.ReadToEndAsync();
        if (!recovery.WaitForExit(60_000))
        {
            try { recovery.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException("Runtime recovery exceeded the 60-second startup budget.");
        }

        Task.WaitAll(stdout, stderr);
        foreach (var line in stdout.Result.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries))
        {
            logger.LogInformation("Runtime recovery: {RecoveryOutput}", line);
        }
        foreach (var line in stderr.Result.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries))
        {
            logger.LogWarning("Runtime recovery: {RecoveryError}", line);
        }

        if (recovery.ExitCode != 0)
        {
            throw new InvalidOperationException(
                $"Runtime recovery failed closed with exit code {recovery.ExitCode}; API startup is blocked.");
        }
    }

    private static int SafePid(Process process)
    {
        try { return process.Id; }
        catch { return -1; }
    }

    private static string ResolveRepoRoot()
    {
        // The canonical installer layout is:
        //   <install-root>\\service_host\\ResearchOS.ServiceHost.exe
        // Prefer the packaged layout over inherited machine/service environment
        // so the self-contained service never resolves to the Windows Program
        // Files parent or another stale development path.
        var packagedRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
        var packagedEntrypoint = Path.Combine(packagedRoot, "tools", "research_os_api", "server.py");
        if (File.Exists(packagedEntrypoint))
        {
            return packagedRoot;
        }

        var configured = Environment.GetEnvironmentVariable("RESEARCH_OS_REPO_ROOT");
        if (!string.IsNullOrWhiteSpace(configured))
        {
            var configuredRoot = Path.GetFullPath(configured);
            var configuredEntrypoint = Path.Combine(configuredRoot, "tools", "research_os_api", "server.py");
            if (Directory.Exists(configuredRoot) && File.Exists(configuredEntrypoint))
            {
                return configuredRoot;
            }
        }

        throw new InvalidOperationException(
            $"Research OS packaged root could not be resolved from {AppContext.BaseDirectory} and RESEARCH_OS_REPO_ROOT does not contain the API entrypoint.");
    }

    private static string ResolvePython(string repoRoot)
    {
        var configured = Environment.GetEnvironmentVariable("RESEARCH_OS_PYTHON_EXE");
        if (!string.IsNullOrWhiteSpace(configured) && File.Exists(configured))
        {
            return Path.GetFullPath(configured);
        }

        var bundled = Path.Combine(repoRoot, "runtime", "python", "python.exe");
        if (File.Exists(bundled))
        {
            return bundled;
        }

        return "python.exe";
    }

    private static string Quote(string value) => $"\"{value.Replace("\"", "\\\"")}\"";

    private static async Task PumpAsync(StreamReader reader, string path, CancellationToken token)
    {
        await using var stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite);
        await using var writer = new StreamWriter(stream) { AutoFlush = true };
        while (!token.IsCancellationRequested)
        {
            // Do not query EndOfStream synchronously: it can block before the
            // asynchronous read starts and prevent the second pipe from draining.
            var line = await reader.ReadLineAsync(token);
            if (line is null)
            {
                break;
            }

            await writer.WriteLineAsync($"[{DateTimeOffset.Now:O}] {line}");
        }
    }

    private static async Task IgnoreCancellation(Task task)
    {
        try { await task; }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) { }
    }
}
