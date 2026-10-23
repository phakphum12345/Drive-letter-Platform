from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("m2_source_integrity_audit.py")
SPEC = importlib.util.spec_from_file_location("m2_source_integrity_audit", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load M.2 source-integrity audit module")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class WorkingTreePurityTests(unittest.TestCase):
    def _repository(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        (root / "sample.py").write_text("print('original')\\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "sample.py"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)

    def test_clean_checkout_matches_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            self.assertTrue(AUDIT.working_tree_matches_head(root))

    def test_modified_tracked_file_does_not_match_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            (root / "sample.py").write_text("print('changed')\\n", encoding="utf-8")
            self.assertFalse(AUDIT.working_tree_matches_head(root))

    def test_staged_change_does_not_match_head(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            (root / "sample.py").write_text("print('staged')\\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "sample.py"], check=True)
            self.assertFalse(AUDIT.working_tree_matches_head(root))

    def test_audit_records_tree_sha_and_cleanliness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._repository(root)
            head = AUDIT.run_git(root, "rev-parse", "HEAD")
            result = AUDIT.audit(root, expected_sha=head)
            self.assertEqual(result["tree_sha"], AUDIT.run_git(root, "rev-parse", "HEAD^{tree}"))
            self.assertTrue(result["working_tree_clean"])


class SourceIntegrityByteClassificationTests(unittest.TestCase):
    def test_detects_bom_only_file_as_corruption(self) -> None:
        findings = AUDIT.classify_bytes("tools/create_change_queue.py", b"\xef\xbb\xbf")
        self.assertIn("BOM_ONLY_EMPTY_FILE", {item["code"] for item in findings})

    def test_detects_bom_prefixed_source(self) -> None:
        findings = AUDIT.classify_bytes("tools/example.py", b"\xef\xbb\xbfprint('x')\n")
        self.assertIn("UTF8_BOM", {item["code"] for item in findings})

    def test_detects_nul_byte_in_text_source(self) -> None:
        findings = AUDIT.classify_bytes("tools/example.py", b"print('x')\x00\n")
        self.assertIn("TEXT_NUL_BYTE", {item["code"] for item in findings})

    def test_authoritative_bom_blob_is_not_misclassified_as_corruption(self) -> None:
        path = "owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1"
        blob_sha = "bb43724cc9cfbbdbc709490ea72a0946e59aa3b1"
        raw_findings = AUDIT.classify_bytes(path, b"\xef\xbb\xbfparam()\n")
        self.assertIn("UTF8_BOM", {item["code"] for item in raw_findings})
        findings = AUDIT.apply_authoritative_bom_policy(path, blob_sha, raw_findings)
        codes = {item["code"] for item in findings}
        self.assertNotIn("UTF8_BOM", codes)
        self.assertIn("AUTHORITATIVE_BOM_MATCH", codes)

    def test_authoritative_desktop_shell_bom_is_not_misclassified(self) -> None:
        path = "apps/research_os_flutter/test/desktop_shell_test.dart"
        blob_sha = "55c9ff4e76455ce20b2a3757f3364deaed38f598"
        raw_findings = AUDIT.classify_bytes(path, b"\xef\xbb\xbfimport 'package:flutter/material.dart';\n")
        self.assertIn("UTF8_BOM", {item["code"] for item in raw_findings})
        findings = AUDIT.apply_authoritative_bom_policy(path, blob_sha, raw_findings)
        codes = {item["code"] for item in findings}
        self.assertNotIn("UTF8_BOM", codes)
        self.assertIn("AUTHORITATIVE_BOM_MATCH", codes)

    def test_bom_exception_does_not_apply_to_different_blob(self) -> None:
        path = "owner_special/installer/scripts/research-os-owner-runtime-quiesce.ps1"
        findings = AUDIT.apply_authoritative_bom_policy(
            path, "0" * 40, AUDIT.classify_bytes(path, b"\xef\xbb\xbfparam()\n")
        )
        self.assertIn("UTF8_BOM", {item["code"] for item in findings})

    def test_does_not_treat_binary_image_nul_as_text_corruption(self) -> None:
        findings = AUDIT.classify_bytes("assets/logo.png", b"\x89PNG\x00binary")
        self.assertEqual(findings, [])

    def test_zero_byte_source_is_reported(self) -> None:
        findings = AUDIT.classify_bytes("lib/main.dart", b"")
        self.assertIn("ZERO_BYTE_TEXT_FILE", {item["code"] for item in findings})

    def test_clean_utf8_source_passes_byte_checks(self) -> None:
        self.assertEqual(AUDIT.classify_bytes("lib/main.dart", "void main() {}\n".encode()), [])


if __name__ == "__main__":
    unittest.main()
