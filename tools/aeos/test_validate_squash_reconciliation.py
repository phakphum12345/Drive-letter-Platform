"""Regression tests ensuring unavailable history never becomes a false pass."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate_squash_reconciliation.py")
VALID = {
    "schema": "aeos.squash-reconciliation.v1", "pr_number": 366,
    "base_sha": "0" * 40, "head_sha": "1" * 40, "merge_sha": "2" * 40,
    "merge_parent_sha": "0" * 40,
    "divergent_paths": ["src/conflict.py"],
    "canonical_conflict_evidence": {"src/conflict.py": {"stale_or_conflicting": True, "evidence": "independent comparison pending"}},
    "accepted_payload_paths": ["src/accepted.py"],
    "accepted_payload_digest": "2" * 40, "accepted_payload_digest_algorithm": "git_commit_sha",
    "independent_forensic_status": "PENDING", "merge_authority": False, "self_certification": False,
}

class ReconciliationValidationTests(unittest.TestCase):
    def invoke(self, payload: dict, stage: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=temp, check=True)
            return subprocess.run([sys.executable, str(SCRIPT), str(manifest), stage], cwd=temp, text=True, capture_output=True, check=False)

    def test_source_stage_fails_closed_when_historical_objects_are_missing(self) -> None:
        result = self.invoke(VALID, "source")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required historical Git commit is unavailable", result.stderr)

    def test_source_stage_rejects_digest_mismatch_before_git_validation(self) -> None:
        payload = dict(VALID, accepted_payload_digest="3" * 40)
        result = self.invoke(payload, "source")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("accepted payload digest does not equal merge commit SHA", result.stderr)

    def test_advanced_base_squash_validates_payload_against_merge_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            (root / "base.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            subprocess.run(["git", "checkout", "-qb", "pr"], cwd=root, check=True)
            (root / "payload.txt").write_text("payload\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "PR payload"], cwd=root, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            subprocess.run(["git", "checkout", "-q", "main"], cwd=root, check=True)
            (root / "upstream.txt").write_text("already on main\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "advance main"], cwd=root, check=True)
            merge_parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            (root / "payload.txt").write_text("payload\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "squash PR payload"], cwd=root, check=True)
            merge = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            payload = dict(VALID, pr_number=999, base_sha=base, head_sha=head, merge_sha=merge,
                merge_parent_sha=merge_parent, divergent_paths=[], canonical_conflict_evidence={},
                accepted_payload_paths=["payload.txt"], accepted_payload_digest=merge)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), str(manifest), "source"],
                cwd=root, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn('"stage": "source"', result.stdout)

    def test_forensic_stage_fails_closed_when_historical_objects_are_missing(self) -> None:
        payload = dict(VALID, independent_forensic_status="VERIFIED")
        result = self.invoke(payload, "forensic")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required historical Git commit is unavailable", result.stderr)

if __name__ == "__main__":
    unittest.main()
