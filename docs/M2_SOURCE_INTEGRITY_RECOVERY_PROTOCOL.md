# M.2 Source Integrity & Recovery Protocol

- **Protocol ID:** M2-SIRP-001
- **Version:** 1.0.0
- **Status:** ACTIVE — investigation protocol; not a recovery certification
- **Scope:** imported Research OS source snapshot, source/UI parity, workflow coverage, Git provenance, and damaged-file recovery
- **Authority:** M.2 audit produces findings and evidence only. It cannot authorize execution, merge, or release. The existing Final Gate remains the sole release authority.

## 1. Objective

Detect and explain source-integrity failures as a connected system, including:
1. tested SHA, checked-out SHA, source SHA, UI/build SHA, artifact SHA, and evidence SHA drift;
2. missing or rewritten Git history and unverifiable source lineage;
3. files omitted from workflow triggers or test/build scopes;
4. damaged files (NUL bytes, BOM-only files, unexpected BOMs, zero-byte/truncated files, invalid encoding, or source that no longer parses);
5. path collisions, accidental moves, wrong-path copies, duplicate basenames, and source files silently shadowed by another path;
6. UI assets or generated artifacts built from a different revision than the source under test.

A green individual workflow is not proof that the repository is whole. A missing workflow run is not a pass. Never repair evidence by weakening a gate.

## 2. Known incident register (evidence-backed, scoped to the current PR investigation)

| ID | Observation | Classification | Required response |
|---|---|---|---|
| SIR-001 | `tools/tests/test_aeos_assurance_universe_compiler.py` previously failed compilation with `source code string cannot contain null bytes`; commit `41f44b5348ccae453a685047e3fb7a5789cd395b` says it replaces the corrupted test. | Historical corruption; current repair requires re-verification | Re-run byte-level scan and compiler/test suite on exact head; preserve prior blob and diff evidence. |
| SIR-002 | The current CI Lite audit reported BOM in 14 files. | Confirmed current-head source-integrity finding | Record raw-byte hashes; compare each file with an authoritative source before repair. Strip BOM only when content otherwise matches trusted source. |
| SIR-003 | `tools/create_change_queue.py` fetched from the PR head decodes from Base64 as `77u/`, i.e. BOM only with no implementation body. | Confirmed empty/corrupt implementation | Do not “fix” by removing BOM. Recover from an identified, trusted source revision or leave blocked with a recovery finding. |
| SIR-004 | `current/BASELINE_TRUTH_CONTRACT.json` references production and canonical commits `565ab068d5a1540ea799b594ff031ba003e068af` and `fab39afc15739c3dc9952f6f21db46d26f54b683`; the Baseline Truth Gate failed because the verifier could not find the anchors in the checked-out Git object graph. | Confirmed provenance/history failure | Recover/verify the original objects from the authoritative repository or revise the contract only through an approved, evidence-backed lineage decision. Never replace anchors with the current HEAD just to pass. |
| SIR-005 | Prior audit history identified expected squash object `14750f63b0c1871b768874f36f6b7ee32e48cc99` as missing from the imported history. | Historical provenance gap; verify against authoritative remotes | Verify the object and its parent/tree relationships from authoritative Git history; record unavailable vs disproven distinctly. |
| SIR-006 | 84 workflow files were previously identified with action references that violated the repository policy requiring full-length commit-SHA pins. Current head contains examples of SHA-pinned actions, but complete policy compliance must be audited across all workflows and nested composite actions. | Historical workflow policy issue; current whole-tree state unproven | Enumerate every `uses:` including local composite actions; require immutable full SHA pins for external actions and validate nested action references. |
| SIR-007 | Several workflow definitions use `paths` filters, including Flutter CI and Production Certification. | Confirmed coverage risk, not proof of a specific skipped run | Build a changed-file-to-workflow coverage matrix. Required universal integrity checks must run for every PR, regardless of path filters. |
| SIR-008 | Source/UI revision mismatch and cross-path file swallowing were raised as historical failure modes, but this audit has not yet proved a specific mismatched UI artifact or overwritten path. | Open hypotheses; not confirmed findings | Require SHA-bound UI/build manifests and path/blob lineage checks before marking either hypothesis confirmed or ruled out. |

The list above is an incident seed, not an exhaustive claim that every historical failure has been discovered. Every new finding must include its evidence reference and exact target SHA.

## 3. Required evidence model

Every audit report must bind all evidence to:
- repository full name and PR number (when applicable);
- immutable target commit SHA and checked-out `git rev-parse HEAD`;
- source baseline repository/ref/commit and retrieval timestamp;
- path, Git blob SHA, byte length, raw-byte SHA-256, detected encoding/BOM/NUL state;
- workflow name, workflow file SHA, run ID, job ID, result, and changed-file coverage;
- UI source SHA, dependency/lockfile identity, build command/toolchain version, artifact SHA-256, and embedded/build manifest where available;
- recovery decision, authoritative source used, before/after hashes, reviewer, and regression tests.

Missing evidence is `UNKNOWN`, not `PASS`. If the source of truth cannot be reached, mark `BLOCKED_SOURCE_UNAVAILABLE`; do not invent a replacement.

## 4. One-pass audit protocol

1. **Freeze the target.** Resolve PR head once, check out that exact SHA, and assert `git rev-parse HEAD == TARGET_SHA`. Do not silently switch to default branch or a moving ref.
2. **Prove provenance.** Check expected source commits and squash objects exist; inspect ancestry, trees, and relevant blobs against authoritative remotes. Keep current work HEAD separate from production truth.
3. **Scan bytes before text.** Walk all tracked files and report NUL bytes, UTF-8 BOM, BOM-only/zero-byte files, invalid UTF-8 where UTF-8 is required, suspiciously truncated files, and parser/compiler errors. Do not rewrite files during the audit.
4. **Compare authoritative file lineage.** For every finding, compare path, mode, blob SHA, raw bytes, and file history against a trusted source commit. Never infer intended content from the filename or a nearby file.
5. **Audit path integrity.** Compare tree paths between baseline and target; detect additions/deletions/renames, case-only collisions, duplicate basenames in critical source/UI areas, and identical or conflicting content at multiple paths. A duplicate basename is a finding for review, not automatic proof of a bug.
6. **Audit workflow coverage.** Enumerate all changed files and all workflows. Evaluate path filters and job-level conditions; identify files with no required validation owner and workflows that were expected but did not run. Require a path-independent source-integrity gate on every PR.
7. **Bind UI and artifact lineage.** Ensure UI tests/builds use the same exact source SHA as the candidate. Record artifact hash and manifest; reject stale caches or artifacts whose source SHA cannot be proven.
8. **Repair by authoritative recovery.** Restore complete content from a verified blob/commit. If no trusted source exists, keep the file blocked; do not create a plausible substitute. Preserve original and recovered hashes and a minimal diff.
9. **Regression and independent verification.** Run parser/compiler, focused tests, repository-wide audit, UI tests/builds, workflow coverage checks, and lineage verification on the exact repaired SHA. Re-run the audit independently.
10. **Final decision.** Emit PASS only if all required checks ran and evidence is complete. Otherwise emit FAIL or BLOCKED with specific findings. No gate suppression, status fabrication, or authority escalation.

## 5. Required invariants

- `TARGET_SHA == checked_out_SHA == tested_source_SHA`, and `tree_sha` must be the Git tree object for that exact commit.
- The audit must fail closed when tracked/index content differs from `HEAD`; record `working_tree_clean` and never present dirty-tree bytes as proof of committed-source identity.
- A release artifact must identify the same source SHA and have a verified artifact hash.
- A path/name match alone never establishes file identity; use Git blob SHA and raw-byte SHA-256.
- Missing historical Git objects cannot be “repaired” by changing a contract to point at an unrelated commit.
- Workflow not triggered, skipped, cancelled, or missing evidence is never treated as successful validation.
- File restoration must not cross project boundaries or replace another path without an explicit rename/move record.
- UI source and backend/API contract versions must be compatible and evidenced, not inferred from a successful compile alone.
- M.2 audit is evidence-producing and advisory; Final Gate retains release authority.

## 6. Exit criteria

The protocol is complete only when the incident register is updated with confirmed/resolved/blocked status; every repaired file has authoritative provenance; all changed files have validation coverage; source/UI/artifact SHAs reconcile; historical anchor availability is independently proven; and the exact target's required gates pass without weakening their assertions.

## 7. Latest evidence update — exact PR head `522057f6e4622535a085d7c55b053fe280a1ddb7`

Audit evidence: [M.2 Source Integrity run 38407689847](https://github.com/phakphum12345/Drive-letter/actions/runs/38407689847). The run checked out the exact PR head and returned **FAIL** with 20 errors and 22 warnings.

Confirmed byte findings:
- 17 files with unexpected UTF-8 BOM, plus the BOM-only `tools/create_change_queue.py` (18 BOM-affected files in total).
- `versions/v1.0.0-draft/docs/00_FOUNDATION/ANEF-001_PROJECT_OVERVIEW.md` contains NUL bytes and fails UTF-8 decoding. Its original bytes are not presumed to be ordinary Markdown; restore only from an authoritative blob.
- 22 duplicate-source-basename groups are review warnings. They are not automatically file collisions; compare Git blob IDs, imports, build targets, and ownership before moving or deleting any file.

Related exact-head failures:
- [CI Lite run 38407687735](https://github.com/phakphum12345/Drive-letter/actions/runs/38407687735) still fails the 6x6 file audit on the 14 Python files whose first character is U+FEFF.
- [Baseline Truth Gate run 38407688988](https://github.com/phakphum12345/Drive-letter/actions/runs/38407688988) cannot find the declared production/canonical history anchors in the checked-out object graph. This is a provenance failure, not permission to replace the anchors with the current head.
- [Production readiness job](https://github.com/phakphum12345/Drive-letter/actions/runs/38407689007/job/115332592608) expects `render.yaml`, `render.staging.yaml`, `scripts/backup-research-os.ps1`, and `scripts/restore-research-os.ps1`. The two render manifests are absent from both the PR head and its base commit, so the evidence points to a workflow/source-snapshot contract mismatch rather than a PR deletion. Do not create placeholder manifests to satisfy the check.

Implementation boundary: the current `tools/m2_source_integrity_audit.py` checks tracked-file bytes, exact checkout SHA, case-fold path collisions, duplicate source basenames, and external action SHA pins. It does **not yet** independently prove historical ancestry, workflow path-filter coverage, UI/build/artifact SHA lineage, or authoritative recovery. These remain open checks and cannot be reported PASS from the current audit.

## 8. Recovery event — ANEF-001 source restoration

The corrupted `ANEF-001_PROJECT_OVERVIEW.md` was restored in commit [`4837ee6ff890f26f5332c02b0f42f0b405fcbe70`](https://github.com/phakphum12345/Drive-letter/commit/4837ee6ff890f26f5332c02b0f42f0b405fcbe70) from the authoritative repository `phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`, commit `565ab068d5a1540ea799b594ff031ba003e068af`.

- Previous target blob: `1f393559390921bb5282c0a93da7cc208b10a971` (M.2 detected NUL and invalid UTF-8).
- Authoritative source blob: `b9a9e9c38300bb13ea9ca8afe32dc5e499af1fd0`.
- Restored target blob: `b9a9e9c38300bb13ea9ca8afe32dc5e499af1fd0` — exact Git blob SHA match.
- Disposition: **restored; independent exact-head re-audit pending**. This does not certify the remaining BOM files, missing source helpers, baseline gate, workflow coverage, UI SHA lineage, or path-shadow warnings.

## 9. Provenance and path findings

The immutable anchors `565ab068d5a1540ea799b594ff031ba003e068af`, `fab39afc15739c3dc9952f6f21db46d26f54b683`, and historical squash object `14750f63b0c1871b768874f36f6b7ee32e48cc99` were found in the authoritative repository `phakphoum38-stack/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`; GitHub's compare API confirms each is an ancestor of that repository's `main`. They are absent from the imported `Drive-letter` object graph because this repository contains a source snapshot rather than that original Git history. The Baseline Truth and M.2 workflows have been updated to fetch authoritative main and check ancestry; their new exact-head CI results are still pending. Do not change the immutable anchors to the snapshot's current HEAD.

The source blob `bb43724cc9cfbbdbc709490ea72a0946e59aa3b1` for `owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1` is identical in the imported tree and authoritative source. Its BOM is source-verified and must be preserved. The audit now allows this exact path/blob pair only; a changed blob does not receive the exception.

The 14 damaged Python helper paths listed in the incident contract were not present in the recursive source trees at either authoritative anchor. In particular, no authoritative `tools/create_change_queue.py` blob was found. These files remain **BLOCKED_SOURCE_UNAVAILABLE** until a trusted branch/blob is found; no guessed replacement will be created.

Sampled same-basename implementations (`apps/research_os_flutter/lib/main.dart`, `owner_special/flutter_app/lib/main.dart`, `v3/flutter_app/lib/main.dart`, plus selected `brain.py` and `service.py` files) have distinct Git blob SHAs. That rules out byte-identical overwriting for those samples, but does not prove that every import/build reference points to the intended implementation. The remaining 22 basename groups still require path/reference ownership review.

## 10. UI source revision check — sampled, not full certification

The three sampled UI entry points below have exact Git blob SHA equality with authoritative production commit `565ab068d5a1540ea799b594ff031ba003e068af` in `phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`:

| Path | Source and target Git blob SHA | Result |
|---|---|---|
| `apps/research_os_flutter/lib/main.dart` | `077a1f64fc2f4572d8323870d17d9dcd93dfb13d` | Exact match |
| `owner_special/flutter_app/lib/main.dart` | `5aea08ec59adb7f70606901a5116dc48484f62d9` | Exact match |
| `v3/flutter_app/lib/main.dart` | `99379d902cc6e468dc8bec077351291c5bb74021` | Exact match |

The Unified 10x10 workflow explicitly checks out its selected `TARGET_SHA` and compares it with `git rev-parse HEAD`. The artifact workflow records `TARGET_SHA` in its website manifest. These are positive controls, but they do not establish that every UI asset, dependency lockfile, generated output, or artifact in this PR was built from the same revision. Full UI/build/artifact lineage remains open.

## 11. Current disposition

**NOT CERTIFIED.**


## 12. Latest exact-head evidence update — 2026-10-13

**Target:** `a183fd6ab46f982cbe1f73dca06674ac74f0e7e6`\
**Decision:** **NOT CERTIFIED — blocking source damage remains.**

### 12.1 CI Lite — exact same target SHA

Run [38411171672](https://github.com/phakphum12345/Drive-letter/actions/runs/38411171672) checked out `a183fd6ab46f982cbe1f73dca06674ac74f0e7e6` and failed in API unit tests after 255 tests ran. The single failing test was `test_candidate_repository_passes_adaptive_6x6_file_audit`; it reported 14 blocking Python syntax findings caused by U+FEFF at line 1:

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

The API unit-test failure caused Flutter setup and Flutter analyze/tests to be skipped in this CI Lite run. The `401`/ `403` entries in the API logs are not the reported failing assertion: the log's only failing test is the source-file audit. Do not relax identity, trial-mode, or owner-authority checks to turn those responses into `200`.

### 12.2 M.2 Source Integrity — exact same target SHA

Run [38411172443](https://github.com/phakphum12345/Drive-letter/actions/runs/38411172443) verified `exact_sha_match=true`, scanned 1,662 tracked files, 86 workflow/composite-action files, and 165 external action references. It returned **17 errors, 1 informational source-verified BOM match, and 22 duplicate-basename review warnings**.

The 17 errors comprise the 14 damaged Python paths above plus three other unexpected-BOM files: `.github/workflows/aeos-master-assurance.yml`, `.gitignore`, and `apps/research_os_flutter/test/desktop_shell_test.dart`. The BOM in `owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1` is an exact authoritative blob match and must be preserved. The 22 duplicate-basename groups are review warnings, not proof of overwrite.

`tools/create_change_queue.py` is specifically confirmed to contain only the UTF-8 BOM bytes (`77u/` in Base64) and no implementation. Its exact path was not found in the authoritative production/canonical trees already reviewed. All 14 helper files remain **BLOCKED_SOURCE_UNAVAILABLE** until a trusted branch/blob is found; do not strip the BOM and leave an empty file, and do not reconstruct implementation from a filename.

### 12.3 Independent gate results and remaining coverage

On `a183fd6ab46f982cbe1f73dca06674ac74f0e7e6`, the Baseline Truth Gate, Workflow Integrity Gate, Unified 10x10 Exact SHA Gate, Research OS Final Gate, and Research OS Unified Final Gate reported success. Those results do not override the failing CI Lite and M.2 source-integrity findings.

Run [38411172505](https://github.com/phakphum12345/Drive-letter/actions/runs/38411172505) failed in V3.5 Master Final Gate production-readiness validation because `render.yaml` is missing; the workflow also requires `render.staging.yaml`, `scripts/backup-research-os.ps1`, and `scripts/restore-research-os.ps1`. Evidence in the incident register says these assets are absent from both the PR base and head, so this is a workflow/asset-contract mismatch, not proof that this PR deleted them. The backup/restore drill was skipped after the missing-asset failure.

Three sampled UI entry-point blobs match the authoritative production source exactly. Full UI asset, dependency-lock, build, generated-output, and release-artifact SHA lineage remains unverified. The current M.2 implementation still does not independently prove workflow path-filter coverage or UI/build/artifact lineage; those checks must remain open rather than be reported as passed.

### 12.4 Required next decision

Restore damaged files only from a verified authoritative blob or branch. Keep the PR blocked where provenance cannot be established. Resolve the production-readiness workflow's required-asset contract against the intended deployment model, with explicit evidence, rather than adding guessed placeholders or weakening the validation. Re-run all relevant checks against one new immutable target SHA and preserve the report and diff.


## 13. Exact source-transfer proof — 2026-10-14

The source-transfer hypothesis is now confirmed for the two deployment manifests. At authoritative source commit `565ab068d5a1540ea799b594ff031ba003e068af` in `phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`, the exact Git blob SHAs are:

- `render.yaml` — `1df582f3078f3e2282fd91de569cc925eab34be2`
- `render.staging.yaml` — `237879fe0b43ae6f76e4edb2750cf96bb0541e06`

Both paths are absent from the inspected `Drive-letter` import branch. Therefore the production-readiness failure is not just a workflow expectation mismatch: the manifests exist in the authoritative source tree and were omitted from this imported snapshot. Restore those exact blobs, then verify destination blob SHAs and run the production-readiness checks; do not create placeholders.

At PR head `e5f9317869430a30c5f258a18d9652238935ae3f`, CI Lite run `38422967217` and M.2 audit run `38422967510` still fail on the 14 BOM-affected Python helper paths. `tools/create_change_queue.py` remains BOM-only and is absent from the authoritative source tree at the inspected production anchor, so it remains blocked pending another trusted recovery source. Baseline Truth Gate run `38422967410` now passes after the authoritative-history check was corrected. Production readiness run `38422967420` still fails on `render.yaml`.

The 22 duplicate-basename warnings remain review-only until each relevant import/build reference is traced to an expected path and blob. Sampled UI entry-point blobs match their authoritative source, and the version-alignment test passes, but complete UI/build/package artifact SHA lineage is still unverified. The PR remains **NOT CERTIFIED**.


## 14. Historical M.2 findings — distinguish corruption from contract drift

Two older observations are retained as historical findings and must not be mislabeled as confirmed source corruption:

- At snapshot commit `c31e9b84976ae150fdd1586cee6b2320c04b6378`, the test `tools/tests/test_aeos_assurance_universe_compiler.py -q` reported **4 passed, 3 failed**. The implementation declared 105 `ASSURANCE_FAMILIES`, while the contract/test expected exactly 100. The additional families were `common_mode_resistance`, `assurance_completeness`, `assurance_of_assurance`, `constitutional_integrity`, and `knowledge_lifecycle_integrity`. This is an implementation-versus-contract cardinality disagreement until the canonical intended count is established; do not delete valid families merely to satisfy a hard-coded assertion.
- In the same source-snapshot review, `tools/copilot_chat/__init__.py` and its related test appeared binary/corrupted in the snapshot renderer. That is a **suspicion**, not proof. Recheck raw bytes, file mode, Git blob SHA, history, and authoritative source before restoring or rewriting either file.

This distinction is mandatory in M.2: byte corruption, source-transfer omission, SHA/provenance drift, path shadowing, and contract/implementation disagreement are separate finding classes and require different repairs.

## 15. Canonical recovery decision contract

**Standard ID:** `M2-SOURCE-INTEGRITY-RECOVERY-001`, version `1.0.0`\
**Authority:** M.2 is diagnostic only. The existing Final Gate remains the release/merge authority.\
**Unknown provenance:** `HOLD`.

The machine-readable `protocol_standard` object in `current/M2_SOURCE_INTEGRITY_RECOVERY_PROTOCOL.json` is the canonical decision contract for this protocol. It supplements the incident history above; it does not overwrite or certify historical findings.

### Required invariants

- Immutable source identity and one exact tested SHA across each evidence bundle.
- Full-path inventory plus byte length and SHA-256 for every tracked file.
- Detection of NUL, BOM, empty, truncated, and invalid-text files.
- Restoration only from a trusted source revision or independently verified recovery artifact.
- UI, API contract, generated asset, and packaged artifact source/version alignment.
- Workflow trigger/path-filter coverage and explicit checkout-SHA verification.
- Fail-closed handling for missing, stale, or ambiguous evidence.
- Full applicable regression and Gate reruns on the new recovery SHA.

### Required evidence

Each run records source repository and commit, target repository/branch and tested commit, parent SHA, path/hash inventories, missing and unexpected paths, case-fold collisions, duplicate-basename review, byte-integrity findings, UI/API/artifact alignment, workflow coverage, restoration provenance, gate results, decision, and decision reasons.

### Decision rules

- **PASS** only when all required evidence is complete and consistent for the exact tested SHA.
- **FAIL** when a verified integrity or consistency invariant is violated.
- **HOLD** when source provenance or required evidence is missing, ambiguous, stale, or independently unverifiable.

These rules do not authorize stripping a BOM from a BOM-only file, synthesizing missing implementation, weakening a failed Gate, treating expected authorization denials as success, or interpreting a green subset of workflows as an overall PASS. Existing incident entries remain evidence snapshots and must be refreshed by new runs before any Final Gate decision.

## 16. Exact-path authoritative history audit — 2026-10-19

A read-only, path-specific commit-history query was run for each of the 14 BOM-affected Python helper paths against both authoritative repositories:

- `phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`
- `phakphoum38-stack/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH`

All 28 repository/path queries returned zero commits touching the exact path. This is stronger than a default-branch listing: the queried commit history did not provide a canonical blob at any of those exact paths. It still does **not** prove that an equivalent implementation never existed under a different filename, directory, repository, or unqueried external source.

**Decision remains `HOLD`.** Do not synthesize implementations, treat the in-repository BOM-only change-queue replacement as canonical, or remove/restore helper files without independently verifying the intended tree and reference graph. Search for trusted alternate-path implementations and compare exact commit, tree, path, mode, and blob SHA before any recovery decision.
