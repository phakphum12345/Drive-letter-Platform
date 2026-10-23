[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$DataDir
)
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}
function Write-RecoveryEvidence([string]$Status, [string]$Message, [object]$Details = $null) {
    $logDir = Join-Path $DataDir 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $record = [ordered]@{
        schema = 'research-os.runtime-auto-recovery/v1'
        captured_at = [DateTimeOffset]::UtcNow.ToString('o')
        status = $Status
        message = $Message
        source_sha = $sourceSha
        package_sha256 = $expectedZipSha
        details = $Details
        user_data_modified = $false
        release_authority = 'FINAL_GATE'
    }
    $path = Join-Path $logDir ('runtime-recovery-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.json')
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding utf8
    Write-Output "RUNTIME_RECOVERY_STATUS=$Status"
    Write-Output "RUNTIME_RECOVERY_EVIDENCE=$path"
}

$sourceSha = $null
$expectedZipSha = $null
$markerPath = $null
$stageRoot = $null
try {
    $root = [IO.Path]::GetFullPath($InstallRoot)
    $data = [IO.Path]::GetFullPath($DataDir)
    $provenancePath = Join-Path $root 'OWNER_SPECIAL_PLATFORM_INSTALL_PROVENANCE.json'
    if (-not (Test-Path -LiteralPath $provenancePath -PathType Leaf)) {
        Write-Output 'RUNTIME_RECOVERY_STATUS=SKIPPED_NO_PACKAGE_PROVENANCE'
        exit 0
    }

    $provenance = Get-Content -LiteralPath $provenancePath -Raw | ConvertFrom-Json
    $sourceSha = [string]$provenance.source_sha
    $expectedZipSha = ([string]$provenance.platform_zip_sha256).ToLowerInvariant()
    $expectedManifestSha = ([string]$provenance.distribution_manifest_sha256).ToLowerInvariant()
    if ($sourceSha -notmatch '^[0-9a-fA-F]{40}$' -or
        $expectedZipSha -notmatch '^[0-9a-f]{64}$' -or
        $expectedManifestSha -notmatch '^[0-9a-f]{64}$') {
        throw 'RECOVERY_BLOCKED: package provenance is missing valid source or SHA256 identity.'
    }

    $zipPath = Join-Path $root "Research-OS-Platform-Windows-x64-$sourceSha.zip"
    if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
        throw 'RECOVERY_BLOCKED: the source-bound canonical Platform ZIP is missing.'
    }
    if ((Get-Sha256 $zipPath) -ne $expectedZipSha) {
        throw 'RECOVERY_BLOCKED: canonical Platform ZIP SHA256 does not match installation provenance.'
    }

    Add-Type -AssemblyName System.IO.Compression
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $manifestEntry = $archive.GetEntry('DISTRIBUTION_MANIFEST.json')
        $manifestHashEntry = $archive.GetEntry('DISTRIBUTION_MANIFEST.sha256')
        if (-not $manifestEntry -or -not $manifestHashEntry) {
            throw 'RECOVERY_BLOCKED: canonical ZIP is missing its distribution manifest.'
        }
        $manifestInput = $manifestEntry.Open()
        $manifestBuffer = [IO.MemoryStream]::new()
        try {
            $manifestInput.CopyTo($manifestBuffer)
            $manifestBytes = $manifestBuffer.ToArray()
        } finally {
            $manifestInput.Dispose()
            $manifestBuffer.Dispose()
        }
        $manifestReader = [IO.StreamReader]::new([IO.MemoryStream]::new($manifestBytes), [Text.Encoding]::UTF8, $true)
        try { $manifestText = $manifestReader.ReadToEnd() } finally { $manifestReader.Dispose() }
        $hashReader = [IO.StreamReader]::new($manifestHashEntry.Open())
        try { $declaredManifestSha = ($hashReader.ReadToEnd().Trim() -split '\s+')[0].ToLowerInvariant() } finally { $hashReader.Dispose() }
        $shaProvider = [Security.Cryptography.SHA256]::Create()
        try { $actualManifestSha = ([BitConverter]::ToString($shaProvider.ComputeHash($manifestBytes))).Replace('-', '').ToLowerInvariant() } finally { $shaProvider.Dispose() }
        if ($actualManifestSha -ne $expectedManifestSha -or $declaredManifestSha -ne $expectedManifestSha) {
            throw 'RECOVERY_BLOCKED: distribution manifest digest does not match installation provenance.'
        }
        $manifest = $manifestText | ConvertFrom-Json
        if ([string]$manifest.source_sha -ne $sourceSha -or [string]$manifest.product_name -ne 'Research OS') {
            throw 'RECOVERY_BLOCKED: package source SHA or product identity mismatch.'
        }

        $allowedPrefixes = @('runtime/python/', 'tools/', 'v3/', 'current/', 'platform/')
        $repairs = [System.Collections.Generic.List[object]]::new()
        $stageRoot = Join-Path $root ('.runtime-recovery-stage-' + [guid]::NewGuid().ToString('N'))
        foreach ($item in @($manifest.files)) {
            $relative = ([string]$item.path).Replace('\', '/')
            $expected = ([string]$item.sha256).ToLowerInvariant()
            if ($expected -notmatch '^[0-9a-f]{64}$') { throw "RECOVERY_BLOCKED: invalid file hash in manifest for $relative." }
            if ([string]::IsNullOrWhiteSpace($relative) -or $relative.StartsWith('/') -or
                $relative -match '^[A-Za-z]:' -or ($relative.Split('/') -contains '..')) {
                throw "RECOVERY_BLOCKED: unsafe manifest path $relative."
            }
            if (-not ($allowedPrefixes | Where-Object { $relative.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { continue }

            $entry = $archive.GetEntry($relative)
            if (-not $entry) { throw "RECOVERY_BLOCKED: manifest file is missing from ZIP: $relative." }
            $destination = [IO.Path]::GetFullPath((Join-Path $root ($relative.Replace('/', '\'))))
            if (-not $destination.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw "RECOVERY_BLOCKED: manifest path escapes install root: $relative."
            }
            $actual = $null
            if (Test-Path -LiteralPath $destination -PathType Leaf) { $actual = Get-Sha256 $destination }
            if ($actual -eq $expected) { continue }

            $stagedPath = Join-Path $stageRoot ($relative.Replace('/', '\'))
            $stagedParent = Split-Path -Parent $stagedPath
            New-Item -ItemType Directory -Path $stagedParent -Force | Out-Null
            $inputStream = $entry.Open()
            try {
                $outputStream = [IO.File]::Open($stagedPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
            } finally { $inputStream.Dispose() }
            if ((Get-Sha256 $stagedPath) -ne $expected) { throw "RECOVERY_BLOCKED: staged file hash verification failed: $relative." }
            $repairs.Add([pscustomobject]@{ path = $relative; expected_sha256 = $expected; observed_sha256 = $actual })
        }

        if ($repairs.Count -eq 0) {
            Write-RecoveryEvidence -Status 'HEALTHY_NO_REPAIR' -Message 'All allowlisted Runtime files match the source-bound manifest.'
            exit 0
        }

        $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
            $exe = [string]$_.ExecutablePath
            $commandLine = [string]$_.CommandLine
            $usesInstallRoot = $commandLine -and ($commandLine.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0)
            ($exe -and $exe.StartsWith((Join-Path $root 'runtime\python').TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) -or
            ($usesInstallRoot -and $commandLine -match '(?i)(server\.py|run_friend_service\.py)')
        } | ForEach-Object {
            [pscustomobject]@{ process_id = [int]$_.ProcessId; name = [string]$_.Name }
        })
        if ($processes.Count -gt 0) {
            throw "RECOVERY_BLOCKED: Runtime files are in use; no process was stopped. PIDs=$(@($processes.process_id) -join ',')."
        }

        $markerPath = Join-Path $data 'logs\runtime-recovery-attempt.json'
        if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
            throw 'RECOVERY_BLOCKED: a previous recovery attempt did not complete successfully; manual review is required.'
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $markerPath) -Force | Out-Null
        [ordered]@{ source_sha = $sourceSha; package_sha256 = $expectedZipSha; started_at = [DateTimeOffset]::UtcNow.ToString('o'); paths = @($repairs.path) } |
            ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $markerPath -Encoding utf8

        foreach ($repair in $repairs) {
            $stagedPath = Join-Path $stageRoot ($repair.path.Replace('/', '\'))
            $destination = Join-Path $root ($repair.path.Replace('/', '\'))
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            if (Test-Path -LiteralPath $destination -PathType Leaf) {
                $backupPath = "$destination.runtime-recovery-backup"
                if (Test-Path -LiteralPath $backupPath) { throw "RECOVERY_BLOCKED: unexpected backup already exists for $($repair.path)." }
                [IO.File]::Replace($stagedPath, $destination, $backupPath, $true)
                Remove-Item -LiteralPath $backupPath -Force
            } else {
                [IO.File]::Move($stagedPath, $destination)
            }
            if ((Get-Sha256 $destination) -ne $repair.expected_sha256) {
                throw "RECOVERY_BLOCKED: post-repair verification failed for $($repair.path)."
            }
        }
        Remove-Item -LiteralPath $markerPath -Force
        $markerPath = $null
        Write-RecoveryEvidence -Status 'RECOVERED' -Message 'Runtime files were restored from the verified source-bound Platform ZIP.' -Details @($repairs)
    } finally {
        $archive.Dispose()
    }
}
catch {
    $message = $_.Exception.Message
    try { Write-RecoveryEvidence -Status 'RECOVERY_BLOCKED' -Message $message } catch {}
    [Console]::Error.WriteLine("RUNTIME_RECOVERY_STATUS=RECOVERY_BLOCKED")
    [Console]::Error.WriteLine($message)
    exit 1
}
finally {
    if ($stageRoot -and (Test-Path -LiteralPath $stageRoot -PathType Container)) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
