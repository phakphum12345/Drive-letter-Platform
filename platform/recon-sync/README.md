# Recon-Sync (review build)

Windows PowerShell 5.1+ utility for explicit status, audit, evidence checks, canonical-ref verification, and detached-worktree sync.

Commands from the repository root:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\platform\recon-sync\recon-sync-engine.ps1 -Command status -RepoRoot .
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\platform\recon-sync\recon-sync-engine.ps1 -Command audit -RepoRoot .
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\platform\recon-sync\recon-sync-engine.ps1 -Command evidence -RepoRoot .
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\platform\recon-sync\recon-sync-engine.ps1 -Command recover -RepoRoot .

status and audit need a valid Git HEAD but do not require the canonical remote. verify and sync require canonical plus canonical/main. sync refuses a dirty source worktree; it does not automatically preserve user changes.

recover currently verifies the newest evidence manifest and hashes only. It does NOT restore files or a worktree and returns EVIDENCE_VERIFIED_ONLY with exit code 3.

Hashes prove content consistency only, not author identity, authenticity, provenance, or completeness. External signing or attestation is required for those claims.

Safety controls: separated Git stdout/stderr, NUL-delimited Git status parsing, manifest schema/run-ID/hash/path validation, path containment, reparse-point rejection, and guarded cleanup of a newly created pristine sync worktree.

Review build only. Do not treat as production-certified until CI and behavior tests pass on Windows PowerShell 5.1.
