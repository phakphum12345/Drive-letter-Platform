#!/usr/bin/env python3
"""Validate explicit AEOS squash-reconciliation provenance."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run_bytes(*args: str) -> bytes:
    return subprocess.check_output(args)


def run(*args: str) -> str:
    return run_bytes(*args).decode("utf-8").strip()


def changed_paths(a: str, b: str) -> set[str]:
    return {line for line in run("git", "diff", "--name-only", a, b).splitlines() if line}


def path_patch(a: str, b: str, path: str) -> bytes:
    return run_bytes("git", "diff", "--no-ext-diff", "--binary", a, b, "--", path)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: validate_squash_reconciliation.py MANIFEST.json [source|forensic]", file=sys.stderr)
        return 2
    stage = sys.argv[2] if len(sys.argv) == 3 else "forensic"
    if stage not in {"source", "forensic"}:
        raise SystemExit("FAIL: unsupported validation stage")

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    required = {
        "schema", "pr_number", "base_sha", "head_sha", "merge_sha",
        "merge_parent_sha", "divergent_paths", "canonical_conflict_evidence",
        "accepted_payload_paths", "accepted_payload_digest", "accepted_payload_digest_algorithm",
        "independent_forensic_status", "merge_authority", "self_certification",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise SystemExit(f"FAIL: missing reconciliation fields: {missing}")
    if data["schema"] != "aeos.squash-reconciliation.v1":
        raise SystemExit("FAIL: unsupported reconciliation schema")
    if data["accepted_payload_digest_algorithm"] != "git_commit_sha":
        raise SystemExit("FAIL: unsupported accepted payload digest algorithm")
    if data["merge_authority"] is not False or data["self_certification"] is not False:
        raise SystemExit("FAIL: reconciliation evidence cannot grant authority or self-certify")
    if stage == "forensic" and data["independent_forensic_status"] != "VERIFIED":
        raise SystemExit("FAIL: independent forensic verification is required")

    # Both stages verify the referenced Git object graph. The source stage permits
    # pending independent forensic status; the forensic stage additionally requires
    # independent verification. Workflows must fetch the manifest's source history
    # explicitly instead of weakening checks when historical objects are absent.
    sha_fields = ("base_sha", "head_sha", "merge_sha", "merge_parent_sha", "accepted_payload_digest")
    for field in sha_fields:
        value = data[field]
        if not isinstance(value, str) or not __import__("re").fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
            raise SystemExit(f"FAIL: {field} is not a full Git object ID")
    if data["merge_sha"] != data["accepted_payload_digest"]:
        raise SystemExit("FAIL: accepted payload digest does not equal merge commit SHA")
    divergent_list = data["divergent_paths"]
    accepted_list = data["accepted_payload_paths"]
    if not isinstance(divergent_list, list) or not all(isinstance(p, str) and p for p in divergent_list):
        raise SystemExit("FAIL: divergent_paths must be a list of non-empty paths")
    if len(set(divergent_list)) != len(divergent_list):
        raise SystemExit("FAIL: duplicate path in divergent_paths")
    if not isinstance(accepted_list, list) or not all(isinstance(p, str) and p for p in accepted_list):
        raise SystemExit("FAIL: accepted_payload_paths must be a list of non-empty paths")
    if len(set(accepted_list)) != len(accepted_list):
        raise SystemExit("FAIL: duplicate path in accepted_payload_paths")
    declared = set(divergent_list)
    evidence = data["canonical_conflict_evidence"]
    if not isinstance(evidence, dict) or set(evidence) != declared:
        raise SystemExit("FAIL: every divergent path needs canonical conflict evidence")
    for path in sorted(declared):
        item = evidence[path]
        if not isinstance(item, dict) or item.get("stale_or_conflicting") is not True or not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise SystemExit(f"FAIL: incomplete stale/conflict proof for divergent path: {path}")
    base = data["base_sha"]
    head = data["head_sha"]
    merge = data["merge_sha"]
    for object_id in (base, head, merge):
        try:
            run("git", "cat-file", "-e", f"{object_id}^{{commit}}")
        except subprocess.CalledProcessError:
            raise SystemExit(f"FAIL: required historical Git commit is unavailable: {object_id}")
    parents = run("git", "rev-list", "--parents", "-n", "1", merge).split()[1:]
    if parents != [data["merge_parent_sha"]]:
        raise SystemExit("FAIL: squash merge must have exactly the declared merge-time parent")
    merge_parent = data["merge_parent_sha"]
    if run("git", "merge-base", base, merge_parent) != base:
        raise SystemExit("FAIL: original PR base is not an ancestor of the merge-time parent")

    head_paths = changed_paths(base, head)
    merge_paths = changed_paths(merge_parent, merge)
    divergent = {
        path for path in head_paths | merge_paths
        if path_patch(base, head, path) != path_patch(merge_parent, merge, path)
    }
    declared = set(data["divergent_paths"])
    if divergent != declared:
        raise SystemExit(f"FAIL: divergent path inventory mismatch: actual={sorted(divergent)} declared={sorted(declared)}")

    evidence = data["canonical_conflict_evidence"]
    if set(evidence) != declared:
        raise SystemExit("FAIL: every divergent path needs canonical conflict evidence")
    for path in sorted(declared):
        item = evidence[path]
        if not item.get("stale_or_conflicting") or not item.get("evidence"):
            raise SystemExit(f"FAIL: incomplete stale/conflict proof for divergent path: {path}")

    accepted = set(data["accepted_payload_paths"])
    if accepted != merge_paths:
        raise SystemExit(f"FAIL: accepted payload inventory mismatch: actual={sorted(merge_paths)} declared={sorted(accepted)}")

    if merge != data["accepted_payload_digest"]:
        raise SystemExit("FAIL: accepted payload digest does not equal merge commit SHA")
    if run("git", "rev-parse", merge) != merge:
        raise SystemExit("FAIL: merge commit cannot be resolved")
    if run("git", "merge-base", base, merge) != base:
        raise SystemExit("FAIL: merge is not based on canonical BASE")

    print(json.dumps({
        "status": "PASS",
        "stage": stage,
        "schema": data["schema"],
        "pr_number": data["pr_number"],
        "base_sha": base,
        "head_sha": head,
        "merge_sha": merge,
        "divergent_paths": sorted(declared),
        "accepted_payload_paths": sorted(accepted),
        "accepted_payload_digest": data["accepted_payload_digest"],
        "independent_forensic_status": data["independent_forensic_status"],
        "merge_authority": data["merge_authority"],
        "self_certification": data["self_certification"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
