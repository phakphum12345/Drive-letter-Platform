# M.2 Source Integrity Forensic Protocol

**Protocol:** `RESEARCH-OS-M2-SOURCE-INTEGRITY-FORENSIC`\
**Contract:** `current/M2_SOURCE_INTEGRITY_FORENSIC_PROTOCOL.json`\
**Status:** Proposed for review\
**Authority:** M.2 diagnoses and traces; FINAL_GATE alone decides release.

## Objective

Find common causes behind source SHA/UI version drift, incomplete workflow inputs, corrupted or truncated files, and files silently merged under the wrong path. The protocol is forensic: preserve evidence first, establish provenance, then repair. It must not make a failed gate green by weakening the gate or inventing missing source.

## Confirmed evidence in Drive-letter PR #1

Audit references:
- PR: https://github.com/phakphum12345/Drive-letter/pull/1
- CI Lite run: https://github.com/phakphum12345/Drive-letter/actions/runs/38405062914
- Baseline Truth Gate run: https://github.com/phakphum12345/Drive-letter/actions/runs/38405064054
- Final Gate run: https://github.com/phakphum12345/Drive-letter/actions/runs/38405063515

### Findings

1. **BOM corruption across 14 Python files.** CI Lite reports U+FEFF at line 1 for `tools/add_parser_regression.py`, `tools/add_resource_translator.py`, `tools/bootstrap_resource_semantic_platform.py`, `tools/create_change_queue.py`, `tools/create_resource_identity_allocator.py`, `tools/create_resource_instance.py`, `tools/create_resource_parser_tests.py`, `tools/create_resource_variables.py`, `tools/fix_resource_builder.py`, `tools/fix_resource_builder_validator.py`, `tools/fix_resource_manifest_collision.py`, `tools/fix_resource_parser_identity.py`, `tools/harden_resource_drift.py`, and `tools/harden_resource_semantic_platform.py`.

2. **A file is BOM-only, not merely BOM-prefixed.** The blob for `tools/create_change_queue.py` is `5f282702bb03ef11d7184d19c80927b47f919764`; its base64 content is `77u/`, i.e. the UTF-8 BOM with no Python source after it. Stripping the BOM would still leave the source missing. Recovery requires a trusted blob/revision.

3. **Immutable history anchors are absent from the evaluated checkout.** Baseline Truth Gate reports missing production commit `565ab068d5a1540ea799b594ff031ba003e068af` and canonical history commit `fab39afc15739c3dc9952f6f21db46d26f54b683`. The current workflow calls `verify_baseline_truth.py --head "$GITHUB_SHA"` without an authoritative truth ref. The correct remediation is to establish whether history was omitted by snapshot import or whether the workflow must fetch the authoritative repository/ref. Do not alter the pinned anchors to match the imported snapshot.

4. **Required deployment assets are missing from the evaluated merge tree.** Production readiness validation fails first on `render.yaml`; it also expects `render.staging.yaml`, `scripts/backup-research-os.ps1`, and `scripts/restore-research-os.ps1`. Determine whether those files were omitted from the snapshot, live under another canonical path, or are incorrectly referenced by the workflow. Do not disable the check.

5. **Workflow results are not a substitute for one coherent source identity.** The PR head and the merge commit are different Git objects. Every UI, audit, build, test, artifact, and gate result must state which SHA/tree it evaluated. Evidence from distinct SHAs cannot be combined into a single PASS.

## Required one-pass investigation

1. Freeze the source and target refs; record repository, branch/ref, commit SHA, tree SHA, workflow run ID, and UI build identity.
2. Preserve the original blobs and checksums before touching suspicious files.
3. Trace each affected path to a trusted source commit/blob. Classify each as intact, BOM-prefixed, BOM-only, NUL-corrupted, empty/truncated, missing, moved, or ambiguous.
4. Compare canonical paths case-sensitively and case-insensitively; detect Unicode-normalization collisions, duplicate basenames, import ambiguities, and rename/path drift.
5. Build the transitive closure of each workflow's local inputs: scripts, contracts, tests, fixtures, generated manifests, deployment files, and referenced evidence.
6. Verify that checkout SHA, expected SHA, UI/source SHA, test results, artifacts, and evidence refer to the same declared tree. In workflows intentionally testing a merge ref, record both PR-head SHA and merge SHA.
7. Restore source only from a trusted blob/revision. If no authoritative copy is found, leave the file on HOLD and report the missing provenance.
8. Run source integrity checks and affected unit/regression tests, then rerun the relevant M.2 trace/impact checks and the full required gates against the exact resulting SHA.
9. Record a machine-readable finding for each root cause, its evidence, repair commit, tests, and remaining uncertainty.

## Decision rules

- **PASS:** all required checks have reproducible evidence for the declared source tree.
- **HOLD:** provenance, path mapping, SHA identity, or required input is unresolved.
- **FAIL:** an invariant is demonstrably violated.
- Missing evidence is never PASS. M.2 does not authorize release or merge.

## Important limitation

This protocol documents verified findings and defines the investigation contract. It does **not** claim that the missing source files have already been restored, that path collisions have all been enumerated, or that the protocol is already wired into CI. Those claims require implementation and fresh evidence tied to a specific commit SHA.
