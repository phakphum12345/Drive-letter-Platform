# M.2 Source Integrity Recovery Protocol

**Protocol ID:** M2-SIRP-001\
**Status:** ACTIVE — recovery is incomplete; Final Gate is NOT authorized\
**Scope:** Source files, manifests, workflow inclusion, UI/build version identity, and path identity for the Drive-letter Research OS snapshot.

## 1. Non-negotiable invariants

1. A result is valid only for the exact Git commit SHA printed by the workflow after checkout. Every required gate in one validation batch must target that same SHA. Never combine green results from different SHAs.
2. The Git commit SHA (40 hex for this repository) identifies the source revision. Per-file SHA-256 values identify file contents. They are different identities and must not be compared as if they were the same algorithm.
3. Never infer original source from a damaged file, neighboring file, filename similarity, UI display, or generated report. Recovery requires a verifiable authoritative source.
4. Do not remove a BOM and call the file recovered unless the remaining bytes are independently verified against an authoritative source. A file that contains only a BOM is empty/destroyed source, not a formatting-only repair.
5. Never weaken or skip a failing gate to obtain a green status. Final Gate remains blocked while any required finding is unresolved or evidence is SHA-mismatched.

## 2. Required source disposition states

- `VERIFIED_SOURCE`: exact source recovered from an authoritative commit/blob/repository and its content hash independently matches.
- `REPAIRED_AND_VERIFIED`: a narrowly scoped transformation is proven semantics-preserving and has regression evidence; retain original and repaired hashes.
- `BLOCKED_SOURCE_UNAVAILABLE`: no authoritative source can be located or proven. Do not invent replacement code; list the path, searched source locations/refs, expected evidence, and unblock condition.
- `BLOCKED_HASH_MISMATCH`: expected and observed file digests differ; do not overwrite the expected digest to fit observed bytes.
- `BLOCKED_PATH_COLLISION`: two or more logical paths resolve to the same normalized path or target; do not silently choose one.
- `BLOCKED_WORKFLOW_OMISSION`: a required file is tracked but not included in the actual audit/build input set.
- `BLOCKED_VERSION_DRIFT`: UI, package, API contract, artifact, or report declares a version/SHA different from the checked-out source identity.

Only the first two states may be considered recovered, and only after their proof records are attached. Blocked states are failures, not warnings.

## 3. Initial incident evidence

Observed in CI Lite run [38405062914](https://github.com/phakphum12345/Drive-letter/actions/runs/38405062914):

- Commit under audit: `c14a8674b9338c711ebbd626dba9ae3cddf7c37a`.
- `test_candidate_repository_passes_adaptive_6x6_file_audit` failed with 14 Python syntax findings: leading U+FEFF/BOM.
- `tools/create_change_queue.py` at that commit decodes to BOM plus newline only. The file contains no recoverable implementation.
- The checked source repository `phakphoum38-stack/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH` did not expose `tools/create_change_queue.py` on its default branch at the same path. This is insufficient evidence to reconstruct it.
- The 14 affected paths are listed in §4. For paths other than `tools/create_change_queue.py`, locate and verify the authoritative source before modifying content. A leading BOM alone does not establish that the rest of a file is authentic.
- The M.2 report returned `M2_SOURCE_INTEGRITY_AUDIT=FAIL`; the excerpt available so far does not include all individual source-hash findings. Do not infer unshown mismatches.

## 4. Damaged file inventory

| Path | Initial disposition | Required next action |
|---|---|---|
| `tools/add_parser_regression.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/add_resource_translator.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/bootstrap_resource_semantic_platform.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/create_change_queue.py` | `BLOCKED_SOURCE_UNAVAILABLE` | Source is BOM-only; recover from a separately proven source |
| `tools/create_resource_identity_allocator.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/create_resource_instance.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/create_resource_parser_tests.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/create_resource_variables.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/fix_resource_builder.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/fix_resource_builder_validator.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/fix_resource_manifest_collision.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/fix_resource_parser_identity.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/harden_resource_drift.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |
| `tools/harden_resource_semantic_platform.py` | `BLOCKED_SOURCE_UNAVAILABLE` pending proof | Locate authoritative blob/commit; compare full content digest |

The inventory's blocked state is intentionally conservative. Promote a file out of a blocked state only after recording the exact authoritative repository, ref/commit, blob SHA, content SHA-256, and verification result. If no source is found, leave it blocked.

## 5. M.2 audit protocol — mandatory checks

### A. Exact revision and evidence binding
- Check out the requested target SHA explicitly.
- Assert `git rev-parse HEAD == TARGET_SHA` before any checks.
- Print `TARGET_SHA`, `CHECKED_OUT_SHA`, workflow run ID/attempt, and tool version into every report.
- Recheck HEAD after tests; fail if any step changes the source revision or runs against a different checkout.
- Bind each evidence item and gate result to the same full commit SHA. A missing SHA is a failure.

### B. Source and file-content integrity
- Enumerate all tracked files with Git; do not rely only on a hand-maintained subset.
- For each manifest entry, verify path existence, object type, expected digest algorithm, and digest value.
- Detect absent files, unexpected files, empty/truncated files, NUL bytes, invalid BOM/encoding, syntax errors, duplicate manifest entries, and stale manifests.
- Preserve the distinction between Git blob SHA and SHA-256 of raw file bytes. Record algorithm and byte-normalization rules explicitly.
- Never update expected hashes merely to make the audit pass. Expected hashes must come from an independently trusted source.

### C. Workflow inclusion and execution completeness
- Build an explicit inventory of required source files, tests, manifests, workflows, and composite actions.
- Compare that inventory to the actual file paths read or tested by each workflow. A workflow file being scanned is not proof that the application files it should validate were scanned.
- Fail with `BLOCKED_WORKFLOW_OMISSION` when any required file is missing from the executed audit input set.
- Verify workflow action references are pinned to full commit SHAs where repository policy requires it; never bypass that policy.
- Emit machine-readable per-path dispositions and per-gate results, including skipped/not-run reasons.

### D. UI / build / API version alignment
- Derive UI version, API contract version, build metadata, installer/package metadata, and evidence report identity from the same source revision or a single canonical version source.
- Compare the UI's displayed source/build SHA against the server/build SHA and release artifact provenance. A matching human-readable version string alone is insufficient.
- Add a negative test that intentionally supplies a stale UI/build SHA and verifies the gate rejects it.
- Fail with `BLOCKED_VERSION_DRIFT` if any surface references another revision or unproven artifact.

### E. Path identity and file collision
- Compare repository paths using both exact Git path and Windows-safe normalized path (case folding, separator normalization, Unicode normalization, trailing dot/space handling).
- Detect duplicate basenames when a manifest, UI, build script, or workflow refers to a basename without a repository-relative path.
- Detect case-only collisions, aliases, traversal, and multiple source paths mapping to one destination path.
- Require repository-relative canonical paths in evidence. Do not silently choose one of two files with the same logical destination.
- Fail with `BLOCKED_PATH_COLLISION` when path identity is ambiguous.

### F. Regression and recovery validation
- For each recovered file, compare full bytes against authoritative content or document and test the exact transformation.
- Run syntax/compile checks, focused tests for the recovered component, the full API test suite, file audit, source-integrity audit, UI/build version alignment, workflow-inclusion audit, and path-collision audit.
- Do not report a gate as passed when it was skipped, not applicable without proof, or ran on a different SHA.
- After any source change, generate a new candidate SHA and rerun all required checks from the beginning against that exact SHA.

## 6. Final Gate entry criteria

Final Gate must remain **BLOCKED** until all of the following are true for one identical candidate SHA:

1. Every required source file is `VERIFIED_SOURCE` or `REPAIRED_AND_VERIFIED`.
2. No `BLOCKED_SOURCE_UNAVAILABLE`, hash mismatch, workflow omission, version drift, or path collision remains.
3. All required gates have completed successfully on the same SHA; none are skipped to conceal a failure.
4. UI/build/API/artifact provenance agrees with the checked-out source revision.
5. Audit manifests and reports are regenerated from that candidate and their own provenance is verified.
6. A read-back confirms the final candidate SHA and the recorded gate evidence.

A source-unavailable blocker cannot be waived by green unrelated checks. Report the blocker and the exact missing evidence instead of claiming Final Gate success.

## 7. Required machine-readable evidence record

Each file disposition must contain at least:

- `path`, `status`, `target_sha`, `observed_blob_sha`, `observed_content_sha256`
- `authoritative_repository`, `authoritative_ref`, `authoritative_commit_sha`, `authoritative_blob_sha`
- `source_comparison_result`, `workflow_ids`, `gate_run_ids`
- `reason`, `missing_evidence`, `unblock_condition`

Use null for unknown values; never fabricate a value. The protocol itself does not mark any code as recovered. Its status is active until the evidence record is complete and all required checks pass.
