#!/usr/bin/env python3
"""Independent, read-only verifier for AEOS squash reconciliation evidence.

Recomputes the PR payload from Git objects. The immutable original base may
precede the actual merge-time parent; compare BASE->HEAD with
MERGE_PARENT->MERGE. This verifier never grants merge authority.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = [
    REPO / "current" / "AEOS_SQUASH_RECONCILIATIONS.json",
    REPO / "current" / "AEOS_SQUASH_RECONCILIATION_PR12.json",
]
OUTPUT = REPO / "independent-forensic-verification.json"
EXPECTED_PORTS = {"8787", "8788", "8790"}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=REPO)


def paths(a: str, b: str) -> set[str]:
    return {p for p in git("diff", "--name-only", a, b).splitlines() if p}


def patch(a: str, b: str, path: str) -> bytes:
    return git_bytes("diff", "--no-ext-diff", "--binary", a, b, "--", path)


def file_at(commit: str, path: str) -> bytes:
    return git_bytes("show", f"{commit}:{path}")


def exists_at(commit: str, path: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"], cwd=REPO,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def parse_acl_services(content: bytes) -> set[str]:
    text = content.decode("utf-8")
    match = re.search(r'"services"\s*:\s*\{(?P<body>.*?)\n\s*\}\s*\n\s*\}', text, re.DOTALL)
    if not match:
        raise ValueError("ACL services object not found")
    return set(re.findall(r'"(\d{4})"\s*:', match.group("body")))


def parse_team_services(content: bytes) -> set[int]:
    return set(json.loads(content.decode("utf-8"))["owner"]["services"])


def verify_one(manifest: Path) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema") != "aeos.squash-reconciliation.v1":
        raise ValueError(f"{manifest.name}: unsupported schema")
    if data.get("independent_forensic_status") != "PENDING":
        raise ValueError(f"{manifest.name}: status must remain PENDING; self-promotion is forbidden")
    if data.get("merge_authority") is not False or data.get("self_certification") is not False:
        raise ValueError(f"{manifest.name}: authority escalation or self-certification")
    base, head, merge, merge_parent = (
        data["base_sha"], data["head_sha"], data["merge_sha"], data["merge_parent_sha"]
    )
    for label, oid in (("BASE", base), ("HEAD", head), ("MERGE", merge), ("MERGE_PARENT", merge_parent)):
        if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise ValueError(f"{manifest.name}: {label} is not a full SHA-1 object ID")
        if git("rev-parse", oid) != oid:
            raise ValueError(f"{manifest.name}: {label} SHA does not resolve exactly")
    parents = git("rev-list", "--parents", "-n", "1", merge).split()[1:]
    if parents != [merge_parent]:
        raise ValueError(f"{manifest.name}: merge must have exactly the declared merge-time parent")
    if git("merge-base", base, merge_parent) != base:
        raise ValueError(f"{manifest.name}: original PR base is not an ancestor of merge-time parent")

    head_paths = paths(base, head)
    accepted = paths(merge_parent, merge)
    divergent = {
        path for path in head_paths | accepted
        if patch(base, head, path) != patch(merge_parent, merge, path)
    }
    if set(data.get("divergent_paths", [])) != divergent:
        raise ValueError(f"{manifest.name}: divergent inventory mismatch: {sorted(divergent)}")
    if set(data.get("accepted_payload_paths", [])) != accepted:
        raise ValueError(f"{manifest.name}: accepted payload inventory mismatch: {sorted(accepted)}")
    if data.get("accepted_payload_digest") != merge:
        raise ValueError(f"{manifest.name}: accepted payload digest is not the exact MERGE SHA")
    evidence = data.get("canonical_conflict_evidence", {})
    if not isinstance(evidence, dict) or set(evidence) != divergent:
        raise ValueError(f"{manifest.name}: conflict evidence must cover exactly the divergent paths")
    for path in divergent:
        item = evidence[path]
        if item.get("stale_or_conflicting") is not True or not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise ValueError(f"{manifest.name}: incomplete conflict proof for {path}")

    # Keep the existing, stronger semantic checks for the historical #366 record.
    if data["pr_number"] == 366:
        expected_divergent = {
            "owner_special/flutter_app/test/team_acl_test.dart",
            "owner_special/team_center_contract.json",
            "owner_special/tests/test_port_topology_contract.py",
        }
        expected_accepted = {
            "current/AEOS_HOLD_RECOVERY_CONTRACT.json",
            "owner_special/research_os_friend/hold_recovery_engine.py",
            "owner_special/tests/test_hold_recovery_engine.py",
        }
        if divergent != expected_divergent or accepted != expected_accepted:
            raise ValueError("legacy #366 semantic inventory changed")
        acl = parse_acl_services(file_at(head, "owner_special/flutter_app/test/team_acl_test.dart"))
        acl_base = parse_acl_services(file_at(base, "owner_special/flutter_app/test/team_acl_test.dart"))
        acl_merge = parse_acl_services(file_at(merge, "owner_special/flutter_app/test/team_acl_test.dart"))
        if acl != EXPECTED_PORTS | {"8789"} or acl_base != EXPECTED_PORTS or acl_merge != EXPECTED_PORTS:
            raise ValueError("legacy #366 ACL topology divergence no longer matches its evidence")
        team = parse_team_services(file_at(head, "owner_special/team_center_contract.json"))
        team_base = parse_team_services(file_at(base, "owner_special/team_center_contract.json"))
        team_merge = parse_team_services(file_at(merge, "owner_special/team_center_contract.json"))
        if team != {8787, 8788, 8789, 8790} or team_base != {8787, 8788, 8790} or team_merge != {8787, 8788, 8790}:
            raise ValueError("legacy #366 Team Center divergence no longer matches its evidence")
        topo = "owner_special/tests/test_port_topology_contract.py"
        if not exists_at(base, topo) or not exists_at(merge, topo) or exists_at(head, topo):
            raise ValueError("legacy #366 topology test lineage no longer matches its evidence")

    return {
        "target_pr": data["pr_number"], "base_sha": base, "head_sha": head,
        "merge_sha": merge, "merge_parent_sha": merge_parent,
        "divergent_paths": sorted(divergent), "accepted_payload_paths": sorted(accepted),
        "accepted_payload_digest": merge,
        "verification_mode": "independent_git_object_payload_reproduction",
        "status": "VERIFIED",
    }


def fail(reason: str) -> int:
    result = {
        "schema": "aeos.squash-reconciliation.independent-forensic.v1",
        "status": "FAIL", "reason": reason,
        "merge_authority": False, "self_certification": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1


def main() -> int:
    try:
        records = [verify_one(path) for path in MANIFESTS if path.is_file()]
        if not records:
            return fail("no reconciliation manifests found")
    except (KeyError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        return fail(str(exc))
    result = {
        "schema": "aeos.squash-reconciliation.independent-forensic.v1",
        "status": "VERIFIED", "records": records,
        "target_prs": [record["target_pr"] for record in records],
        "merge_authority": False, "self_certification": False,
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
