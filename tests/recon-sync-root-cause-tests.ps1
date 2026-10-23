[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RepoRoot)
$ErrorActionPreference='Stop'
$engine=Join-Path $RepoRoot 'platform\recon-sync\recon-sync-engine.ps1'
$tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile($engine,[ref]$tokens,[ref]$errors)|Out-Null
if($errors.Count){throw ('Parse failure: '+(($errors|%{$_.Message})-join '; '))}
$text=Get-Content -LiteralPath $engine -Raw
foreach($required in @('Get-GitStatusRecords','Test-NoReparsePoints','EVIDENCE_VERIFIED_ONLY','authenticity=''NOT_PROVEN''','--porcelain=v1','Initialize-LocalIdentity')){if($text.IndexOf($required,[StringComparison]::OrdinalIgnoreCase)-lt 0){throw "Missing root-cause control: $required"}}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('recon-sync-test-'+[guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $temp|Out-Null
try{
 foreach($path in @('platform\recon-sync\recon-sync-engine.ps1','platform\recon-sync\recon-sync-center.hta','platform\recon-sync\README.md','START-RECON-SYNC.cmd','recon-sync-audit.cmd')){$dest=Join-Path $temp $path;New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force|Out-Null;Copy-Item -LiteralPath (Join-Path $RepoRoot $path) -Destination $dest -Force}
 & git.exe -C $temp init -q;if($LASTEXITCODE-ne 0){throw 'git init failed'}
 & git.exe -C $temp config user.email 'recon-test@example.invalid';& git.exe -C $temp config user.name 'Recon Test'
 & git.exe -C $temp add --all;if($LASTEXITCODE-ne 0){throw 'git add failed'};& git.exe -C $temp commit -qm 'test fixture';if($LASTEXITCODE-ne 0){throw 'git commit failed'}
 $ep=Join-Path $temp 'platform\recon-sync\recon-sync-engine.ps1'
 $o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ep -Command status -RepoRoot $temp -Json 2>&1;if($LASTEXITCODE-ne 0){throw ('status failed: '+($o-join [Environment]::NewLine))};$s=($o-join [Environment]::NewLine)|ConvertFrom-Json;if($s.status-ne 'PASS'){throw "status expected PASS, got $($s.status)"}
 $o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ep -Command audit -RepoRoot $temp -Json 2>&1;if($LASTEXITCODE-ne 0){throw ('audit failed: '+($o-join [Environment]::NewLine))};$a=($o-join [Environment]::NewLine)|ConvertFrom-Json;if($a.status-ne 'PASS'){throw "audit expected PASS, got $($a.status)"}
 $o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ep -Command evidence -RepoRoot $temp -Json 2>&1;if($LASTEXITCODE-ne 0){throw ('evidence failed: '+($o-join [Environment]::NewLine))};$e=($o-join [Environment]::NewLine)|ConvertFrom-Json;if($e.status-ne 'PASS_LOCAL_ONLY'){throw "expected PASS_LOCAL_ONLY, got $($e.status)"}
 $o=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ep -Command recover -RepoRoot $temp -Json 2>&1;if($LASTEXITCODE-ne 3){throw "recover must return exit 3 for evidence-only: $($o-join [Environment]::NewLine)"};$r=($o-join [Environment]::NewLine)|ConvertFrom-Json;if($r.status-ne 'EVIDENCE_VERIFIED_ONLY'-or $r.recovery_performed-ne $false){throw 'recover falsely reported restoration'}
}finally{Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue}
Write-Output 'PASS: parser; status/audit without canonical remote; local-only evidence; truthful recover exit code'
