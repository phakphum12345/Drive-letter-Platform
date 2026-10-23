#!/usr/bin/env python3
"""M.2 source-integrity audit: byte-level checks bound to an exact Git SHA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {
    ".py", ".pyi", ".dart", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".md",
    ".txt", ".ps1", ".psm1", ".psd1", ".sh", ".bash", ".bat", ".cmd",
    ".xml", ".gradle", ".properties", ".php", ".sql", ".ini", ".cfg",
    ".conf", ".workflow", ".lock", ".gitignore",
}
SOURCE_SUFFIXES = {".py", ".pyi", ".dart", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".php", ".ps1", ".psm1", ".sh", ".bash"}
EXEMPT_EMPTY_NAMES = {".gitkeep", ".keep"}
TRUSTED_SOURCE_BOM_BLOBS = {
    "owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1": {
        "blob_sha": "bb43724cc9cfbbdbc709490ea72a0946e59aa3b1",
        "repository": "phakphum12345/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH",
        "commit": "565ab068d5a1540ea799b594ff031ba003e068af",
    },
    "apps/research_os_flutter/test/desktop_shell_test.dart": {
        "blob_sha": "55c9ff4e76455ce20b2a3757f3364deaed38f598",
        "repository": "phakphoum38-stack/ENTERPRISE_API_ARCHITECTURE_LOGIC_TH",
        "commit": "e67e2cf707c015212cb8cd3843c9f3a13ab4e80c",
    },
}
EXTERNAL_ACTION_RE = re.compile(r"^\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)", re.MULTILINE)


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def classify_bytes(path: str, raw: bytes) -> list[dict[str, str]]:
    """Return byte-integrity findings without attempting to mutate or repair the file."""
    p = Path(path)
    suffix = p.suffix.lower()
    findings: list[dict[str, str]] = []
    is_text = suffix in TEXT_SUFFIXES or p.name in {".gitignore", ".gitattributes", ".editorconfig"}
    if is_text and b"\x00" in raw:
        findings.append({"severity": "error", "code": "TEXT_NUL_BYTE", "path": path, "message": "text/source file contains NUL bytes"})
    if is_text and raw.startswith(b"\xef\xbb\xbf"):
        if raw == b"\xef\xbb\xbf":
            findings.append({"severity": "error", "code": "BOM_ONLY_EMPTY_FILE", "path": path, "message": "file contains only a UTF-8 BOM; restore from authoritative source"})
        else:
            findings.append({"severity": "error", "code": "UTF8_BOM", "path": path, "message": "unexpected UTF-8 BOM; compare raw bytes with authoritative source before repair"})
    if is_text and not raw and p.name not in EXEMPT_EMPTY_NAMES:
        findings.append({"severity": "error", "code": "ZERO_BYTE_TEXT_FILE", "path": path, "message": "tracked text/source file is zero bytes"})
    if is_text and raw and not raw.startswith(b"\xef\xbb\xbf"):
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            findings.append({"severity": "error", "code": "INVALID_UTF8", "path": path, "message": f"UTF-8 decode failed at byte {exc.start}"})
    return findings


def apply_authoritative_bom_policy(
    path: str, git_blob_sha: str, findings: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Do not flag a BOM as corruption when the exact blob is source-verified."""
    source = TRUSTED_SOURCE_BOM_BLOBS.get(path)
    if not source or git_blob_sha != source["blob_sha"]:
        return findings
    retained = [item for item in findings if item["code"] != "UTF8_BOM"]
    retained.append({
        "severity": "info",
        "code": "AUTHORITATIVE_BOM_MATCH",
        "path": path,
        "message": (
            f"UTF-8 BOM is byte-identical to authoritative blob {git_blob_sha} "
            f"at {source['repository']}@{source['commit']}; not classified as corruption"
        ),
    })
    return retained


def tracked_paths(root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if output.returncode:
        raise RuntimeError(output.stderr.decode("utf-8", "replace").strip() or "git ls-files failed")
    return [item.decode("utf-8", "surrogateescape") for item in output.stdout.split(b"\x00") if item]


def working_tree_matches_head(root: Path) -> bool:
    """Return whether tracked files match the checked-out commit."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(result.stderr.strip() or "git diff HEAD failed")


def verify_baseline_history(root: Path, truth_ref: str | None) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    """Verify declared baseline anchors exist and descend from the authoritative ref."""
    if not truth_ref:
        return "UNKNOWN", [], {}
    contract_path = root / "current" / "BASELINE_TRUTH_CONTRACT.json"
    if not contract_path.is_file():
        return "FAIL", [{
            "severity": "error",
            "code": "BASELINE_CONTRACT_MISSING",
            "path": "current/BASELINE_TRUTH_CONTRACT.json",
            "message": "baseline truth contract is missing",
        }], {}
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        anchors = {
            "production": contract["production_code_truth"]["commit"],
            "canonical": contract["canonical_main_history_truth"]["commit"],
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return "FAIL", [{
            "severity": "error",
            "code": "BASELINE_CONTRACT_INVALID",
            "path": "current/BASELINE_TRUTH_CONTRACT.json",
            "message": str(exc),
        }], {}

    findings: list[dict[str, str]] = []
    verified: dict[str, str] = {}
    for label, sha in anchors.items():
        exists = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, text=True, check=False,
        )
        if exists.returncode != 0:
            findings.append({
                "severity": "error", "code": "BASELINE_ANCHOR_MISSING",
                "path": "current/BASELINE_TRUTH_CONTRACT.json",
                "message": f"{label} anchor {sha} is absent from fetched Git objects",
            })
            continue
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, truth_ref],
            capture_output=True, text=True, check=False,
        )
        if ancestor.returncode == 1:
            findings.append({
                "severity": "error", "code": "BASELINE_ANCHOR_NOT_ANCESTOR",
                "path": "current/BASELINE_TRUTH_CONTRACT.json",
                "message": f"{label} anchor {sha} is not an ancestor of {truth_ref}",
            })
        elif ancestor.returncode != 0:
            findings.append({
                "severity": "error", "code": "BASELINE_TRUTH_REF_UNAVAILABLE",
                "path": "current/BASELINE_TRUTH_CONTRACT.json",
                "message": ancestor.stderr.strip() or f"unable to verify {label} against {truth_ref}",
            })
        else:
            verified[label] = sha
    return ("FAIL" if findings else "PASS"), findings, verified


def audit(
    root: Path,
    expected_sha: str | None = None,
    truth_ref: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    head = run_git(root, "rev-parse", "HEAD")
    expected = (expected_sha or os.environ.get("TARGET_SHA") or head).strip()
    findings: list[dict[str, str]] = []
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        findings.append({"severity": "error", "code": "INVALID_TARGET_SHA", "path": ".", "message": "TARGET_SHA must be a full 40-character lowercase Git commit SHA"})
    elif head != expected:
        findings.append({"severity": "error", "code": "CHECKOUT_SHA_MISMATCH", "path": ".", "message": f"expected {expected}, checked out {head}"})

    tree_sha = run_git(root, "rev-parse", "HEAD^{tree}")
    working_tree_clean = False
    try:
        working_tree_clean = working_tree_matches_head(root)
        if not working_tree_clean:
            findings.append({"severity": "error", "code": "WORKTREE_CONTENT_MISMATCH", "path": ".", "message": "tracked working-tree or index content differs from the checked-out commit; audit result is not commit-pure"})
    except RuntimeError as exc:
        findings.append({"severity": "error", "code": "WORKTREE_COMPARISON_FAILED", "path": ".", "message": str(exc)})

    baseline_history_status, baseline_findings, baseline_anchors_verified = verify_baseline_history(root, truth_ref)
    findings.extend(baseline_findings)

    paths = tracked_paths(root)
    casefold_paths: dict[str, list[str]] = defaultdict(list)
    basename_sources: dict[str, list[str]] = defaultdict(list)
    raw_sha256: dict[str, str] = {}
    git_blob_sha_by_path: dict[str, str] = {}
    scanned = 0
    for rel in paths:
        file_path = root / rel
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            findings.append({"severity": "error", "code": "TRACKED_FILE_UNREADABLE", "path": rel, "message": str(exc)})
            continue
        scanned += 1
        raw_sha256[rel] = hashlib.sha256(raw).hexdigest()
        blob_sha = run_git(root, "rev-parse", f"HEAD:{rel}")
        git_blob_sha_by_path[rel] = blob_sha
        file_findings = classify_bytes(rel, raw)
        findings.extend(apply_authoritative_bom_policy(rel, blob_sha, file_findings))
        casefold_paths[rel.casefold()].append(rel)
        if Path(rel).suffix.lower() in SOURCE_SUFFIXES:
            basename_sources[Path(rel).name.casefold()].append(rel)

    for folded, members in sorted(casefold_paths.items()):
        if len(members) > 1:
            findings.append({"severity": "error", "code": "CASEFOLD_PATH_COLLISION", "path": ";".join(sorted(members)), "message": "multiple tracked paths collapse to the same case-insensitive path"})
    for basename, members in sorted(basename_sources.items()):
        if len(members) > 1:
            findings.append({"severity": "warning", "code": "DUPLICATE_SOURCE_BASENAME_REVIEW", "path": ";".join(sorted(members)), "message": "duplicate source basename across paths; review import/reference resolution; not automatically a defect"})

    action_files = [
        p for p in paths
        if (p.startswith(".github/workflows/") and Path(p).suffix.lower() in {".yml", ".yaml"})
        or (p.startswith(".github/actions/") and Path(p).name in {"action.yml", "action.yaml"})
    ]
    action_refs: list[dict[str, str]] = []
    for rel in action_files:
        try:
            content = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in EXTERNAL_ACTION_RE.finditer(content):
            action, ref = match.group(1), match.group(2)
            item = {"path": rel, "action": action, "ref": ref}
            action_refs.append(item)
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                findings.append({"severity": "error", "code": "ACTION_NOT_PINNED_TO_FULL_SHA", "path": rel, "message": f"{action}@{ref} is not pinned to a full 40-character commit SHA"})

    counts: dict[str, int] = defaultdict(int)
    for item in findings:
        counts[item["severity"]] += 1
    status = "FAIL" if counts.get("error", 0) else "PASS" if baseline_history_status == "PASS" else "UNKNOWN"
    return {
        "schema_version": "1.0.0",
        "protocol_id": "M2-SIRP-001",
        "contract": "M2_SOURCE_INTEGRITY_RECOVERY",
        "repository_root": str(root),
        "target_sha": expected,
        "checked_out_sha": head,
        "tree_sha": tree_sha,
        "exact_sha_match": head == expected,
        "working_tree_clean": working_tree_clean,
        "authoritative_truth_ref": truth_ref,
        "baseline_history_status": baseline_history_status,
        "baseline_anchors_verified": baseline_anchors_verified,
        "files_scanned": scanned,
        "workflow_and_composite_action_files_scanned": len(action_files),
        "external_action_references_scanned": len(action_refs),
        "finding_counts": dict(sorted(counts.items())),
        "status": status,
        "findings": findings,
        "raw_sha256_by_path": raw_sha256,
        "git_blob_sha_by_path": git_blob_sha_by_path,
        "limitations": [
            "This implementation checks tracked-file bytes, exact checkout SHA and tree SHA, tracked/index cleanliness against HEAD, case-fold path collisions, duplicate source basenames, external action SHA pins, and baseline-anchor ancestry when an authoritative truth ref is supplied.",
            "It does not yet independently prove workflow path-filter coverage, UI/build/artifact SHA lineage, or authoritative recovery. Those remain open protocol checks.",
            "A clean byte scan does not certify semantic correctness or authorize release."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-sha", default=None)
    parser.add_argument("--truth-ref", default=None, help="Authoritative source-history ref containing immutable baseline anchors")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        report = audit(args.root, args.expected_sha, args.truth_ref)
    except (OSError, RuntimeError) as exc:
        print(f"M2_SOURCE_INTEGRITY_AUDIT=BLOCKED: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    print(f"M2_SOURCE_INTEGRITY_AUDIT={report['status']}")
    return 1 if report["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
