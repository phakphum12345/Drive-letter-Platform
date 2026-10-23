[CmdletBinding()]
param([ValidateSet('status','sync','verify','audit','evidence','recover')][string]$Command='status',[switch]$Json,[string]$RepoRoot)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { throw 'Cannot determine repository root.' }; $RepoRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$script:Root=(Resolve-Path -LiteralPath $RepoRoot).Path
$script:EvidenceRoot=Join-Path $script:Root 'evidence\recon-sync'
$script:RunId='recon-{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'),([guid]::NewGuid().ToString('N').Substring(0,8))
$script:RunDir=Join-Path $script:EvidenceRoot $script:RunId
$script:CanonicalSha=''; $script:LocalSha=''; $script:PreservationRef=''; $script:CleanWorktree=''; $script:RecoveryPerformed=$false; $script:Provenance='UNATTESTED'

function ConvertTo-NativeArgument {
 param([Parameter(Mandatory=$true)][AllowEmptyString()][string]$Value)
 if ($Value.Length -eq 0) { return '""' }; if ($Value -notmatch '[\s"]') { return $Value }
 $sb=New-Object System.Text.StringBuilder; [void]$sb.Append('"'); $slashes=0
 foreach ($ch in $Value.ToCharArray()) {
  if ($ch -eq '\') { $slashes++; continue }
  if ($ch -eq '"') { [void]$sb.Append(('\' * (2*$slashes+1))); [void]$sb.Append('"'); $slashes=0; continue }
  if ($slashes -gt 0) { [void]$sb.Append(('\' * $slashes)); $slashes=0 }; [void]$sb.Append($ch)
 }
 if ($slashes -gt 0) { [void]$sb.Append(('\' * (2*$slashes))) }; [void]$sb.Append('"'); return $sb.ToString()
}
function Invoke-Git {
 param([Parameter(Mandatory=$true)][string[]]$GitArgs,[string]$WorkingDirectory=$script:Root)
 $psi=New-Object System.Diagnostics.ProcessStartInfo; $psi.FileName=(Get-Command git.exe -ErrorAction Stop).Source; $psi.WorkingDirectory=$WorkingDirectory; $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
 $psi.Arguments=(($GitArgs | ForEach-Object { ConvertTo-NativeArgument ([string]$_) }) -join ' ')
 $proc=New-Object System.Diagnostics.Process; $proc.StartInfo=$psi; if (-not $proc.Start()) { throw 'Unable to start git.exe.' }
 $outTask=$proc.StandardOutput.ReadToEndAsync(); $errTask=$proc.StandardError.ReadToEndAsync(); $proc.WaitForExit(); $out=$outTask.Result; $err=$errTask.Result; $code=$proc.ExitCode; $proc.Dispose()
 if ($code -ne 0) { $detail=$err.Trim(); if ([string]::IsNullOrWhiteSpace($detail)) { $detail=$out.Trim() }; throw ("git {0} failed (exit {1}): {2}" -f ($GitArgs -join ' '),$code,$detail) }; return $out
}
function Get-GitStatusRecords {
 $raw=Invoke-Git @('status','--porcelain=v1','-z','--untracked-files=all'); $records=New-Object System.Collections.Generic.List[object]
 if ([string]::IsNullOrEmpty($raw)) { return ,@() }; $parts=$raw.Split([char]0)
 for ($i=0;$i -lt $parts.Length;$i++) { $record=$parts[$i]; if ([string]::IsNullOrEmpty($record)) { continue }; if ($record.Length -lt 4) { throw 'Malformed git status record.' }; $xy=$record.Substring(0,2); $path=$record.Substring(3); $n=$path.Replace('\','/')
  if ($n -ne 'evidence/recon-sync' -and -not $n.StartsWith('evidence/recon-sync/',[StringComparison]::OrdinalIgnoreCase)) { $records.Add([pscustomobject]@{Status=$xy;Path=$path;Display=($xy+' '+$path)}) }
  if ($xy -match '[RC]' -and $i+1 -lt $parts.Length) { $i++ }
 }; return ,$records.ToArray()
}
function Get-WorkingTreeChanges { return ,@((Get-GitStatusRecords) | ForEach-Object { $_.Display }) }
function Get-Sha256File {
 param([Parameter(Mandatory=$true)][string]$Path); $s=[IO.File]::OpenRead($Path); $h=[Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($h.ComputeHash($s))).Replace('-','').ToLowerInvariant() } finally { $s.Dispose(); $h.Dispose() }
}
function Write-JsonUtf8NoBom {
 param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)]$Value)
 $parent=Split-Path -Parent $Path; if (-not (Test-Path -LiteralPath $parent -PathType Container)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
 $json=ConvertTo-Json -InputObject $Value -Depth 16; [IO.File]::WriteAllText($Path,($json+[char]10),(New-Object System.Text.UTF8Encoding($false)))
}
function New-Result {
 param([string]$Status,[string]$Operation,[string]$ErrorMessage='',[string]$RecoveryStatus='NOT_APPLICABLE')
 return [ordered]@{schema_version=2;status=$Status;operation=$Operation;run_id=$script:RunId;canonical_sha=$script:CanonicalSha;local_sha=$script:LocalSha;preservation_ref=$script:PreservationRef;worktree=$script:CleanWorktree;recovery_performed=[bool]$script:RecoveryPerformed;recovery_status=$RecoveryStatus;evidence_integrity='CONTENT_HASHES_ONLY';provenance=$script:Provenance;authenticity='NOT_PROVEN';evidence=$script:RunDir;timestamp=(Get-Date).ToUniversalTime().ToString('o');errors=@($(if (-not [string]::IsNullOrWhiteSpace($ErrorMessage)) {$ErrorMessage}))}
}
function Write-Result {
 param([Parameter(Mandatory=$true)]$ResultObject); New-Item -ItemType Directory -Force -Path $script:RunDir | Out-Null
 Write-JsonUtf8NoBom -Path (Join-Path $script:RunDir 'result.json') -Value $ResultObject
 if ($Json) { ConvertTo-Json -InputObject $ResultObject -Depth 16 } else { '[{0}] {1} {2}' -f $ResultObject.status,$ResultObject.operation,$ResultObject.run_id; 'Canonical : {0}' -f $ResultObject.canonical_sha; 'Local     : {0}' -f $ResultObject.local_sha; 'Evidence  : {0}' -f $ResultObject.evidence; foreach($e in $ResultObject.errors){if($e){'ERROR     : {0}' -f $e}} }
}
function Initialize-LocalIdentity { $script:LocalSha=(Invoke-Git @('rev-parse','--verify','HEAD^{commit}')).Trim(); if($script:LocalSha -notmatch '^[0-9a-fA-F]{40,64}$'){throw 'HEAD did not resolve to a valid commit ID.'} }
function Initialize-CanonicalIdentity {
 $url=(Invoke-Git @('remote','get-url','canonical')).Trim(); if([string]::IsNullOrWhiteSpace($url)){throw 'canonical remote URL is empty.'}
 $script:CanonicalSha=(Invoke-Git @('rev-parse','--verify','refs/remotes/canonical/main^{commit}')).Trim(); if($script:CanonicalSha -notmatch '^[0-9a-fA-F]{40,64}$'){throw 'canonical/main tracking ref is not a valid commit ID.'}; Initialize-LocalIdentity; return $url
}
function Test-NoReparsePoints {
 param([Parameter(Mandatory=$true)][string]$Root,[Parameter(Mandatory=$true)][string]$FilePath)
 $rootFull=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'; $full=[IO.Path]::GetFullPath($FilePath)
 if(-not $full.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw "Evidence path escapes run directory: $FilePath"}
 $cursor=$rootFull.TrimEnd('\'); $relative=$full.Substring($rootFull.Length)
 foreach($part in ($relative -split '[\\/]')) { if([string]::IsNullOrWhiteSpace($part)){throw 'Empty evidence path component.'}; $cursor=Join-Path $cursor $part; if(Test-Path -LiteralPath $cursor){$item=Get-Item -LiteralPath $cursor -Force;if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint)-ne 0){throw "Reparse point is not allowed in evidence: $cursor"}} }
}
function Test-EvidenceRun {
 param([Parameter(Mandatory=$true)][string]$Directory); $dir=(Resolve-Path -LiteralPath $Directory).Path; $mp=Join-Path $dir 'evidence.json'
 if(-not(Test-Path -LiteralPath $mp -PathType Leaf)){throw "Evidence manifest missing: $mp"}; Test-NoReparsePoints -Root $dir -FilePath $mp
 try{$m=Get-Content -LiteralPath $mp -Raw | ConvertFrom-Json -ErrorAction Stop}catch{throw "Evidence manifest JSON is invalid: $($_.Exception.Message)"}
 if([string]$m.schema_version -ne '1'){throw 'Unsupported or missing evidence schema_version (expected 1).'}; if([string]$m.run_id -cne (Split-Path $dir -Leaf)){throw 'Evidence run_id does not match containing directory.'}; if($null -eq $m.files -or @($m.files).Count -lt 1){throw 'Evidence manifest has no files.'}
 $seen=@{}
 foreach($e in @($m.files)){ $rel=[string]$e.path
  if([string]::IsNullOrWhiteSpace($rel)-or $rel.Contains(':')-or $rel.StartsWith('/')-or $rel.StartsWith('\')-or $rel -match '(^|[\\/])\.{1,2}([\\/]|$)'-or $rel -match '[\x00-\x1f]'){throw "Unsafe evidence path: $rel"}
  $key=$rel.Replace('\','/').ToLowerInvariant(); if($seen.ContainsKey($key)){throw "Duplicate evidence path: $rel"}; $seen[$key]=$true
  $expected=[string]$e.sha256; if($expected -notmatch '^[0-9a-fA-F]{64}$'){throw "Invalid SHA-256 value: $rel"}
  $file=Join-Path $dir $rel; if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "Evidence file missing: $rel"}; Test-NoReparsePoints -Root $dir -FilePath $file
  if((Get-Sha256File -Path $file) -cne $expected.ToLowerInvariant()){throw "Evidence hash mismatch: $rel"}
 }; return $m
}
function Test-RequiredComponents {
 foreach($r in @('platform\recon-sync\recon-sync-center.hta','platform\recon-sync\README.md','START-RECON-SYNC.cmd','recon-sync-audit.cmd')){if(-not(Test-Path -LiteralPath (Join-Path $script:Root $r) -PathType Leaf)){throw "Required Recon-Sync component missing: $r"}}
}
try {
 switch($Command){
  'status' { Initialize-LocalIdentity; $c=@(Get-WorkingTreeChanges); $s=if($c.Count -eq 0){'PASS'}else{'DIRTY'}; $msg=if($c.Count -eq 0){''}else{'Working tree has changes; sync is blocked until reviewed and preserved.'}; Write-Result (New-Result -Status $s -Operation status -ErrorMessage $msg); if($s -ne 'PASS'){exit 2} }
  'audit' { Initialize-LocalIdentity; $t=$null;$pe=$null;[Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Root 'platform\recon-sync\recon-sync-engine.ps1'),[ref]$t,[ref]$pe)|Out-Null;if($pe.Count){throw ('PowerShell parse errors: '+(($pe|%{$_.Message}) -join '; '))};Test-RequiredComponents
   $forbidden=@('versions','artifact-*','forensic_*','workflow-intelligence-audit-*');$bad=@();foreach($item in @(Get-GitStatusRecords)){$p=([string]$item.Path).Replace('\','/');foreach($pat in $forbidden){$rx=[regex]::Escape($pat).Replace('\*','.*');if($p -match ('(^|/)'+$rx+'($|/)')){$bad+=$p;break}}};if($bad.Count){throw ('Forbidden paths detected: '+(($bad|Select-Object -Unique)-join ', '))};Write-Result (New-Result -Status PASS -Operation audit) }
  'verify' { Initialize-CanonicalIdentity|Out-Null;$remote=((Invoke-Git @('ls-remote','canonical','refs/heads/main')).Trim() -split '\s+')[0];if($remote -notmatch '^[0-9a-fA-F]{40,64}$'){throw 'Unable to resolve canonical/main from remote.'};if($remote -cne $script:CanonicalSha){throw "canonical/main differs from tracking ref; remote=$remote fetched=$($script:CanonicalSha)"};Write-Result (New-Result -Status PASS -Operation verify) }
  'sync' { Initialize-LocalIdentity;$c=@(Get-WorkingTreeChanges);if($c.Count){throw ('Sync refused: source worktree is dirty; changes are not automatically preserved: '+(($c|Select-Object -First 8)-join '; '))};$url=(Invoke-Git @('remote','get-url','canonical')).Trim();if([string]::IsNullOrWhiteSpace($url)){throw 'canonical remote URL is empty.'};Invoke-Git @('fetch','--no-tags','canonical','main')|Out-Null;$script:CanonicalSha=(Invoke-Git @('rev-parse','--verify','refs/remotes/canonical/main^{commit}')).Trim();$remote=((Invoke-Git @('ls-remote','canonical','refs/heads/main')).Trim()-split '\s+')[0];if($remote -notmatch '^[0-9a-fA-F]{40,64}$'-or $remote -cne $script:CanonicalSha){throw 'Canonical main changed during sync or could not be verified.'}
   $wt=Join-Path ([IO.Directory]::GetParent($script:Root).FullName) ((Split-Path $script:Root -Leaf)+'-canonical-'+$script:RunId);if(Test-Path -LiteralPath $wt){throw "Target worktree exists: $wt"};$created=$false
   try{New-Item -ItemType Directory -Force -Path $script:RunDir|Out-Null;Write-JsonUtf8NoBom -Path (Join-Path $script:RunDir 'sync-intent.json') -Value ([ordered]@{schema_version=1;run_id=$script:RunId;intended_path=$wt;canonical_sha=$script:CanonicalSha;timestamp=(Get-Date).ToUniversalTime().ToString('o')});Invoke-Git @('worktree','add','--detach',$wt,$script:CanonicalSha)|Out-Null;$created=$true;$script:CleanWorktree=$wt;$head=(Invoke-Git @('rev-parse','--verify','HEAD^{commit}') $wt).Trim();if($head -cne $script:CanonicalSha){throw 'New worktree HEAD does not match canonical SHA.'};if(-not [string]::IsNullOrEmpty((Invoke-Git @('status','--porcelain=v1','-z','--untracked-files=all') $wt))){throw 'New worktree is not clean.'};Write-JsonUtf8NoBom -Path (Join-Path $script:RunDir 'manifest.json') -Value ([ordered]@{schema_version=1;run_id=$script:RunId;canonical_url=$url;canonical_sha=$script:CanonicalSha;source_sha=$script:LocalSha;preservation='NOT_PERFORMED_SOURCE_WAS_CLEAN';clean_worktree=$wt;provenance='UNATTESTED';authenticity='NOT_PROVEN';timestamp=(Get-Date).ToUniversalTime().ToString('o')});Write-Result (New-Result -Status PASS -Operation sync)}
   catch{$failure=$_.Exception.Message;if($created -and (Test-Path -LiteralPath $wt -PathType Container)){try{$head=(Invoke-Git @('rev-parse','--verify','HEAD^{commit}') $wt).Trim();$state=Invoke-Git @('status','--porcelain=v1','-z','--untracked-files=all') $wt;if($head -ceq $script:CanonicalSha -and [string]::IsNullOrEmpty($state)){Invoke-Git @('worktree','remove',$wt)|Out-Null;$script:CleanWorktree=''}else{$failure+=' | Cleanup skipped; worktree retained at '+$wt}}catch{$failure+=' | Cleanup failed safely; inspect '+$wt+' : '+$_.Exception.Message}};throw $failure}
  }
  'evidence' { Initialize-LocalIdentity;$available=$false;try{$url=(Invoke-Git @('remote','get-url','canonical')).Trim();$sha=(Invoke-Git @('rev-parse','--verify','refs/remotes/canonical/main^{commit}')).Trim();if($url -and $sha -match '^[0-9a-fA-F]{40,64}$'){$script:CanonicalSha=$sha;$available=$true}}catch{$available=$false};New-Item -ItemType Directory -Force -Path $script:RunDir|Out-Null;$cp=Join-Path $script:RunDir 'canonical.json';Write-JsonUtf8NoBom -Path $cp -Value ([ordered]@{schema_version=1;run_id=$script:RunId;canonical_sha=$script:CanonicalSha;canonical_identity_available=$available;local_sha=$script:LocalSha;provenance='UNATTESTED';authenticity='NOT_PROVEN';timestamp=(Get-Date).ToUniversalTime().ToString('o')});Write-JsonUtf8NoBom -Path (Join-Path $script:RunDir 'evidence.json') -Value ([ordered]@{schema_version=1;run_id=$script:RunId;files=@(@{path='canonical.json';sha256=(Get-Sha256File -Path $cp)});timestamp=(Get-Date).ToUniversalTime().ToString('o')});$null=Test-EvidenceRun -Directory $script:RunDir;$s=if($available){'PASS'}else{'PASS_LOCAL_ONLY'};Write-Result (New-Result -Status $s -Operation evidence) }
  'recover' { if(-not(Test-Path -LiteralPath $script:EvidenceRoot -PathType Container)){throw 'No Recon-Sync evidence directory exists.'};$c=@(Get-ChildItem -LiteralPath $script:EvidenceRoot -Directory|Where-Object{$_.Name -like 'recon-*' -and (Test-Path -LiteralPath (Join-Path $_.FullName 'evidence.json') -PathType Leaf)}|Sort-Object LastWriteTimeUtc -Descending);if(-not $c.Count){throw 'No completed evidence run exists.'};$latest=$c[0];$null=Test-EvidenceRun -Directory $latest.FullName;$script:CleanWorktree='evidence verified only: '+$latest.FullName;Write-Result (New-Result -Status EVIDENCE_VERIFIED_ONLY -Operation recover -ErrorMessage 'No files or worktree were restored; manifest-listed hashes only were checked.' -RecoveryStatus NOT_PERFORMED);exit 3 }
 }
} catch { try{Write-Result (New-Result -Status FAIL -Operation $Command -ErrorMessage $_.Exception.Message)}catch{Write-Error $_};exit 1 }
