# M.2 Source Damage Recovery Protocol v2

- **Protocol ID:** M2-SDRP-002
- **Version:** 2.0.0
- **Status:** ACTIVE — recovery protocol; current PR remains NOT CERTIFIED
- **Target:** `phakphum12345/Drive-letter#1`
- **Audit baseline:** `ac785dbbe5b2b91788e28c2aef498585de6a8d44`
- **Authority:** M.2 records evidence and decisions only. **FINAL_GATE** remains the sole release authority.

## Purpose

This protocol closes the gap between a byte-integrity scan and a full source-transfer proof. It specifically addresses historical SHA/UI version drift, missing workflow coverage, files omitted during repository import, BOM/NUL/truncation damage, and same-basename files that may resolve to the wrong path.

## Evidence snapshot

At the audit baseline `ac785dbbe5b2b91788e28c2aef498585de6a8d44`, the recorded CI evidence is:

| Gate | Run | Result |
|---|---:|---|
| Research OS CI Lite | [38598089877](https://github.com/phakphum12345/Drive-letter/actions/runs/38598089877) | **FAIL** — 14 Python files start with U+FEFF |
| M.2 Source Integrity | [38598089748](https://github.com/phakphum12345/Drive-letter/actions/runs/38598089748) | **FAIL** — 17 errors, 1 informational authoritative-BOM match, 22 duplicate-basename review warnings |
| Baseline Truth | [38598089017](https://github.com/phakphum12345/Drive-letter/actions/runs/38598089017) | PASS on this target |
| V3.5 Master Final Gate | [38598089806](https://github.com/phakphum12345/Drive-letter/actions/runs/38598089806) | PASS on this target |

M.2 reported 1,664 tracked files, 86 workflow/composite-action files and 165 external action references. A successful Baseline Truth Gate proves only its own contract; it does not clear the source damage or certify UI/artifact lineage.

## Confirmed damage and transfer findings

### A. Fourteen Python helper paths remain blocked

The CI Lite source audit reports U+FEFF at line 1 in:

- `tools/add_parser_regression.py`
- `tools/add_resource_translator.py`
- `tools/bootstrap_resource_semantic_platform.py`
- `tools/create_change_queue.py`
- `tools/create_resource_identity_allocator.py`
- `tools/create_resource_instance.py`
- `tools/create_resource_parser_tests.py`
- `tools/create_resource_variables.py`
- `tools/fix_resource_builder.py`
- `tools/fix_resource_builder_validator.py`
- `tools/fix_resource_manifest_collision.py`
- `tools/fix_resource_parser_identity.py`
- `tools/harden_resource_drift.py`
- `tools/harden_resource_semantic_platform.py`

Do not strip the BOM and declare these files repaired. Compare raw bytes and Git blob SHA with an identified authoritative branch/blob first.

### B. `tools/create_change_queue.py` is BOM-only

The PR-head content decodes from Base64 as `77u/`, which represents only the UTF-8 BOM. No implementation body is present. The exact path was not found in the authoritative production/canonical trees previously reviewed. Status is **BLOCKED_SOURCE_UNAVAILABLE** until another trusted branch/blob is identified. Do not reconstruct implementation from the filename.

### C. Three additional unexpected-BOM files

- `.github/workflows/aeos-master-assurance.yml`
- `.gitignore`
- `apps/research_os_flutter/test/desktop_shell_test.dart`

Compare their raw bytes against authoritative sources before deciding whether to remove the BOM. Preserve `owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1` because its BOM is part of an exact authoritative blob match.

### D. Two deployment manifests were omitted during source transfer

At authoritative source commit `565ab068d5a1540ea799b594ff031ba003e068af` in `phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`:

- `render.yaml` — blob `1df582f3078f3e2282fd91de569cc925eab34be2`
- `render.staging.yaml` — blob `237879fe0b43ae6f76e4edb2750cf96bb0541e06`

Both are absent from the inspected imported target. Restore the exact blobs and verify destination blob SHAs. The workflow also requires `scripts/backup-research-os.ps1` and `scripts/restore-research-os.ps1`; investigate those paths against the authoritative tree and explicitly record whether each should exist. Never add placeholder files just to satisfy the job.

### E. Path collision / shadowing is not yet proven

M.2 reports 22 duplicate-basename groups. A duplicate basename is a review signal, not proof that one file swallowed another. For each group, trace import statements, package roots, build target configuration, UI surface ownership, file mode and blob SHA. Do not merge, rename, delete or overwrite until the expected path is evidenced.

### F. UI SHA equality is only sampled

Three `main.dart` entry points matched their authoritative source blobs, but that does not prove that all UI assets, dependency lockfiles, generated sources, build caches, installers or release artifacts came from the same source revision. Require a machine-readable build manifest binding target SHA, source tree, lockfile hashes, toolchain, cache identity, output digest and artifact SHA-256.

### G. Stale run versus current head

A CI run that checked out a prior PR merge commit or earlier head is historical evidence only. Record separately:
- PR head SHA;
- synthetic merge SHA, if applicable;
- checked-out SHA;
- tested source SHA;
- M.2 report target SHA;
- UI/build/artifact source SHA.

Any required mismatch is `STALE_EVIDENCE` or `FAIL`, never PASS. Rerun affected checks after the branch moves.

## One-pass procedure

1. **Freeze target:** resolve one immutable PR head SHA and verify `git rev-parse HEAD`; record merge SHA separately.
2. **Build the source inventory:** for every tracked path, capture mode, Git blob SHA, raw SHA-256, byte length, NUL/BOM/encoding state and parser result.
3. **Prove source lineage:** compare candidate paths and blobs with authoritative production/canonical trees and relevant history. Distinguish exact match, changed content, missing in target, missing in source, and unavailable source.
4. **Classify missing files:** determine whether a path is an import omission, intended deletion, workflow contract mismatch or unknown. Do not infer intent from a workflow alone.
5. **Audit path resolution:** trace imports, package manifests, project files, build scripts and UI routing to the exact path and blob used.
6. **Audit workflow coverage:** calculate changed paths against workflow triggers, job-level conditions, reusable workflows and composite actions. Every changed executable/UI/contract file must have an explicit validating gate. Required integrity checks must not be hidden behind narrow path filters.
7. **Bind UI and artifact:** require the exact target SHA in build metadata and the published artifact manifest; hash dependency locks and outputs; reject stale cache/artifact evidence.
8. **Recover minimally:** restore exact trusted blobs only. Record old blob/hash, source repository/ref/commit/blob, new blob/hash, file mode, diff and focused regression tests. If source is unavailable, retain BLOCKED status.
9. **Run tests on one SHA:** syntax/compiler checks, focused regressions, full M.2 scan, workflow coverage, UI/build tests and artifact lineage checks.
10. **Independent re-audit:** rerun M.2 against the same new immutable target SHA and confirm every artifact/report names that SHA.
11. **Decision:** PASS only if all required checks ran and evidence reconciles. Otherwise emit FAIL, BLOCKED_SOURCE_UNAVAILABLE, UNKNOWN or STALE_EVIDENCE. No gate suppression or fabricated green status.

## Non-negotiable invariants

- `TARGET_SHA == CHECKED_OUT_SHA == TESTED_SOURCE_SHA == M2_REPORT_SHA`.
- UI/build/artifact evidence must bind to the same target SHA; artifact hashes must be recorded.
- Git blob SHA and raw-byte SHA-256, not filename alone, establish byte identity.
- A source-verified BOM must be preserved; a BOM-only file is missing source, not a formatting problem.
- Workflow-skipped, missing, stale or unbound evidence is not success.
- A same-basename warning does not authorize an automatic move or overwrite.
- M.2 is not release authority; FINAL_GATE is the only release authority.

## Exit criteria

The PR remains **NOT CERTIFIED** until the 14 damaged helpers are restored from trusted sources or explicitly blocked, `create_change_queue.py` has a verified implementation, BOM findings are adjudicated against source bytes, omitted manifests are restored exactly, the backup/restore scripts have evidence-backed dispositions, path groups are traced, UI/build/artifact lineage is proven, workflow coverage is machine-checked, and all required gates pass on one exact target SHA.
