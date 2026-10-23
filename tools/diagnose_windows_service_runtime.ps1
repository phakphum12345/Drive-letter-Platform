[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\Research OS",
    [string]$OwnerRoot = "$env:ProgramFiles\Research OS Owner Special",
    [string]$ApiServiceName = "ResearchOSService",
    [string]$OwnerServiceName = "ResearchOSOwnerFriendService",
    [string]$ApiDataDir = "$env:ProgramData\ResearchOS",
    [string]$OwnerDataDir = "$env:ProgramData\ResearchOSOwnerSpecial",
    [ValidateRange(1, 65535)][int]$ApiPort = 8787,
    [ValidateRange(1, 65535)][int]$OwnerPort = 8790,
    [ValidateRange(1, 1440)][int]$EventLookbackMinutes = 30,
    [ValidateRange(1, 1000)][int]$LogTailLines = 100,
    [string]$OutputPath
)

$ErrorActionPreference = 'Continue'
$startedAt = Get-Date
$findings = [System.Collections.Generic.List[object]]::new()

function Add-Finding {
    param([string]$Severity, [string]$Code, [string]$Message, [object]$Evidence = $null)
    $findings.Add([pscustomobject]@{
        severity = $Severity
        code = $Code
        message = $Message
        evidence = $Evidence
    })
}

function Protect-CommandLine {
    param([AllowNull()][string]$CommandLine)
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $null }
    # Keep useful process identity while redacting common inline credential arguments.
    $safe = $CommandLine -replace '(?i)(--?(?:token|password|passwd|secret|api[-_]?key|authorization)\s+)(?:"[^"]*"|\S+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)((?:token|password|passwd|secret|api[-_]?key|authorization)\s*=\s*)(?:"[^"]*"|\S+)', '$1<REDACTED>'
    return $safe
}

function Protect-LogLine {
    param([AllowNull()][string]$Line)
    if ($null -eq $Line) { return $null }
    $safe = $Line -replace '(?i)((?:token|password|passwd|secret|api[-_]?key|authorization)\s*[:=]\s*)(?:"[^"]*"|\S+)', '$1<REDACTED>'
    $safe = $safe -replace '(?i)(--?(?:token|password|passwd|secret|api[-_]?key|authorization)\s+)(?:"[^"]*"|\S+)', '$1<REDACTED>'
    return $safe
}

function Get-ServiceEvidence {
    param([string]$Name)
    try {
        $svc = Get-CimInstance -ClassName Win32_Service -Filter "Name='$($Name.Replace("'","''"))'" -ErrorAction Stop
        if (-not $svc) {
            return [pscustomobject]@{ name = $Name; registered = $false; state = 'MISSING' }
        }
        return [pscustomobject]@{
            name = $svc.Name
            display_name = $svc.DisplayName
            registered = $true
            state = $svc.State
            start_mode = $svc.StartMode
            process_id = [int]$svc.ProcessId
            exit_code = $svc.ExitCode
            service_specific_exit_code = $svc.ServiceSpecificExitCode
            path_name = $svc.PathName
            start_name = $svc.StartName
        }
    } catch {
        Add-Finding 'WARN' 'SERVICE_QUERY_FAILED' "Could not query service $Name" $_.Exception.Message
        return [pscustomobject]@{ name = $Name; registered = $null; state = 'QUERY_FAILED'; error = $_.Exception.Message }
    }
}

function Get-LogEvidence {
    param([string]$DataDir, [string]$Label)
    $candidates = @(
        (Join-Path $DataDir 'logs'),
        (Join-Path $DataDir 'service\logs'),
        (Join-Path $DataDir 'logs\service')
    ) | Select-Object -Unique
    $result = [System.Collections.Generic.List[object]]::new()
    foreach ($dir in $candidates) {
        if (-not (Test-Path -LiteralPath $dir -PathType Container)) { continue }
        foreach ($file in @(Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match '(?i)(service|api|stdout|stderr|\.log$|\.txt$)'
        })) {
            try {
                $lines = @(Get-Content -LiteralPath $file.FullName -Tail $LogTailLines -ErrorAction Stop | ForEach-Object { Protect-LogLine -Line $_ })
                $result.Add([pscustomobject]@{
                    component = $Label
                    path = $file.FullName
                    length = $file.Length
                    last_write_time = $file.LastWriteTime.ToString('o')
                    tail = $lines
                    empty = ($file.Length -eq 0)
                })
            } catch {
                $result.Add([pscustomobject]@{ component = $Label; path = $file.FullName; read_error = $_.Exception.Message })
            }
        }
    }
    return @($result)
}

function Test-LocalHttpEndpoint {
    param([string]$Name, [string]$Uri)
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-RestMethod -Uri $Uri -TimeoutSec 3 -ErrorAction Stop
        $watch.Stop()
        return [pscustomobject]@{
            name = $Name; uri = $Uri; reachable = $true; elapsed_ms = $watch.ElapsedMilliseconds
            status_code = 200; payload = $response
        }
    } catch {
        $watch.Stop()
        $statusCode = $null
        try { if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode } } catch {}
        return [pscustomobject]@{
            name = $Name; uri = $Uri; reachable = $false; elapsed_ms = $watch.ElapsedMilliseconds
            status_code = $statusCode; error_type = $_.Exception.GetType().FullName; error = $_.Exception.Message
        }
    }
}

Write-Host 'Collecting read-only Research OS Windows service evidence...'
$services = @(
    Get-ServiceEvidence -Name $ApiServiceName
    Get-ServiceEvidence -Name $OwnerServiceName
)

$processes = @()
try {
    $runtimePaths = @(
        (Join-Path $InstallRoot 'runtime\python\python.exe'),
        (Join-Path $OwnerRoot 'runtime\python\python.exe')
    ) | ForEach-Object {
        try { [IO.Path]::GetFullPath($_).TrimEnd('\') } catch { $_ }
    }
    $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | Where-Object {
        $path = $null
        if ($_.ExecutablePath) { try { $path = [IO.Path]::GetFullPath($_.ExecutablePath).TrimEnd('\') } catch {} }
        ($path -and ($runtimePaths -contains $path)) -or
        $_.Name -match '(?i)^ResearchOS.*ServiceHost\.exe$'
    } | ForEach-Object {
        [pscustomobject]@{
            process_id = [int]$_.ProcessId
            parent_process_id = [int]$_.ParentProcessId
            name = $_.Name
            executable_path = $_.ExecutablePath
            creation_date = if ($_.CreationDate) { ([datetime]$_.CreationDate).ToString('o') } else { $null }
            command_line = Protect-CommandLine -CommandLine $_.CommandLine
            role_hints = @(
                if ($_.CommandLine -match '(?i)run_friend_service\.py') { 'owner_friend_entrypoint' }
                if ($_.CommandLine -match '(?i)(^|[\\/])server\.py(\s|$)') { 'research_os_api_entrypoint' }
                if ($_.Name -match '(?i)ResearchOS.*ServiceHost\.exe$') { 'service_host' }
            )
        }
    })
} catch {
    Add-Finding 'WARN' 'PROCESS_QUERY_FAILED' 'Could not enumerate relevant processes' $_.Exception.Message
}

$listenerEvidence = @()
$portsToInspect = @($ApiPort, $OwnerPort) | Select-Object -Unique
foreach ($port in $portsToInspect) {
    try {
        $connections = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop)
        foreach ($connection in $connections) {
            $owner = $processes | Where-Object { $_.process_id -eq [int]$connection.OwningProcess } | Select-Object -First 1
            $listenerEvidence += [pscustomobject]@{
                port = $port
                local_address = $connection.LocalAddress
                owning_process_id = [int]$connection.OwningProcess
                owning_process = $owner
                process_was_in_runtime_inventory = [bool]$owner
            }
        }
    } catch {
        if ($_.FullyQualifiedErrorId -notmatch 'NoMatching|InstanceNotFound') {
            Add-Finding 'WARN' 'LISTENER_QUERY_FAILED' "Could not query listening socket for port $port" $_.Exception.Message
        }
    }
}

$http = @(
    Test-LocalHttpEndpoint -Name 'research_os_api_health' -Uri "http://127.0.0.1:$ApiPort/health"
    Test-LocalHttpEndpoint -Name 'owner_friend_health' -Uri "http://127.0.0.1:$OwnerPort/owner/health"
)

$serviceOwnership = @()
foreach ($service in $services) {
    if (-not $service.registered -or -not $service.process_id) { continue }
    $hostProcess = @($processes | Where-Object { $_.process_id -eq [int]$service.process_id })
    $children = @($processes | Where-Object { $_.parent_process_id -eq [int]$service.process_id })
    $serviceOwnership += [pscustomobject]@{
        service_name = $service.name
        service_state = $service.state
        service_process_id = [int]$service.process_id
        service_host_in_inventory = ($hostProcess.Count -gt 0)
        direct_relevant_children = $children
        runtime_child_process_ids = @($children | Where-Object { $_.name -ieq 'python.exe' } | ForEach-Object process_id)
    }
    if ($service.state -eq 'Running' -and $hostProcess.Count -eq 0) {
        Add-Finding 'WARN' 'SERVICE_PID_NOT_IN_INVENTORY' "Service $($service.name) PID $($service.process_id) was not found among the inventoried service hosts." @{
            service_name = $service.name; service_process_id = [int]$service.process_id
        }
    }
}
$logEvidence = @(
    Get-LogEvidence -DataDir $ApiDataDir -Label 'research_os_api'
    Get-LogEvidence -DataDir $OwnerDataDir -Label 'owner_friend'
)

$eventEvidence = @()
$eventStart = (Get-Date).AddMinutes(-$EventLookbackMinutes)
foreach ($logName in @('Application','System')) {
    try {
        $events = @(Get-WinEvent -FilterHashtable @{ LogName = $logName; StartTime = $eventStart } -MaxEvents 500 -ErrorAction Stop |
            Where-Object {
                $_.Message -match "(?i)$([regex]::Escape($ApiServiceName))|$([regex]::Escape($OwnerServiceName))|Research OS API|ResearchOS\.ServiceHost|python\.exe" -or
                ($logName -eq 'System' -and $_.ProviderName -match 'Service Control Manager')
            } | Select-Object -First 60)
        foreach ($event in $events) {
            $eventEvidence += [pscustomobject]@{
                log = $logName
                time_created = $event.TimeCreated.ToString('o')
                provider = $event.ProviderName
                event_id = $event.Id
                level = $event.LevelDisplayName
                message = $event.Message
            }
        }
    } catch {
        Add-Finding 'INFO' 'EVENT_LOG_UNAVAILABLE' "Could not read $logName event log" $_.Exception.Message
    }
}

$apiRuntime = $processes | Where-Object { $_.role_hints -contains 'research_os_api_entrypoint' }
$ownerRuntime = $processes | Where-Object { $_.role_hints -contains 'owner_friend_entrypoint' }
if ($apiRuntime.Count -gt 0 -and $ownerRuntime.Count -gt 0) {
    Add-Finding 'INFO' 'SHARED_RUNTIME_IN_USE' 'API and Owner Friend entrypoints are running under an inventoried bundled Python runtime; cleanup must identify the exact service-owned process, not just the interpreter path.' @{
        api_pids = @($apiRuntime | ForEach-Object process_id)
        owner_friend_pids = @($ownerRuntime | ForEach-Object process_id)
    }
}
foreach ($service in $services) {
    if ($service.registered -and $service.state -ne 'Running') {
        Add-Finding 'ERROR' 'SERVICE_NOT_RUNNING' "Service $($service.name) is $($service.state)" $service
    }
}
foreach ($endpoint in $http) {
    if (-not $endpoint.reachable) {
        Add-Finding 'ERROR' 'HTTP_HEALTH_FAILED' "Endpoint $($endpoint.name) did not return a successful response" $endpoint
    }
}
foreach ($listener in $listenerEvidence) {
    if ($listener.local_address -in @('0.0.0.0','::')) {
        Add-Finding 'WARN' 'NON_LOOPBACK_LISTENER' "Port $($listener.port) is listening on a wildcard address" $listener
    }
}

$report = [pscustomobject]@{
    schema = 'research-os.windows-service-diagnostics/v1'
    captured_at = $startedAt.ToString('o')
    computer = $env:COMPUTERNAME
    read_only = $true
    no_processes_stopped = $true
    parameters = [pscustomobject]@{
        install_root = $InstallRoot; owner_root = $OwnerRoot
        api_service = $ApiServiceName; owner_service = $OwnerServiceName
        api_port = $ApiPort; owner_port = $OwnerPort
        event_lookback_minutes = $EventLookbackMinutes
    }
    services = $services
    relevant_processes = $processes
    service_process_ownership = $serviceOwnership
    listeners = $listenerEvidence
    http_health = $http
    log_tails = $logEvidence
    events = $eventEvidence
    findings = @($findings)
    summary = [pscustomobject]@{
        service_count = $services.Count
        process_count = $processes.Count
        listener_count = $listenerEvidence.Count
        failed_http_checks = @($http | Where-Object { -not $_.reachable }).Count
        error_findings = @($findings | Where-Object severity -eq 'ERROR').Count
        warning_findings = @($findings | Where-Object severity -eq 'WARN').Count
        diagnostic_status = 'COLLECTED_NOT_CERTIFIED'
    }
}

$json = $report | ConvertTo-Json -Depth 10
if ($OutputPath) {
    $fullOutputPath = [IO.Path]::GetFullPath($OutputPath)
    $parent = Split-Path -Parent $fullOutputPath
    if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Set-Content -LiteralPath $fullOutputPath -Value $json -Encoding UTF8
    Write-Host "DIAGNOSTIC_REPORT=$fullOutputPath"
} else {
    Write-Output $json
}
Write-Host "DIAGNOSTIC_FINDINGS=$($findings.Count)"
Write-Host 'DIAGNOSTIC_STATUS=COLLECTED_NOT_CERTIFIED'
