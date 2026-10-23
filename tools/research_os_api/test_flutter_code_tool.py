from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import flutter_code_tool as tool


class FlutterCodeToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        project = self.root / "apps" / "research_os_flutter"
        project.mkdir(parents=True)
        (project / "lib").mkdir()
        (project / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "RESEARCH_OS_CODE_ROOT": str(self.root),
            "RESEARCH_OS_CODE_OWNER_IDS": "owner@example.com",
            "RESEARCH_OS_FLUTTER_COMMAND": "flutter",
        })
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def test_project_and_file_read(self) -> None:
        projects = tool.project_map()
        self.assertIn("research_os_flutter", projects)
        payload = tool.read_file("research_os_flutter", "lib/main.dart")
        self.assertEqual(payload["content"], "void main() {}\n")

    def test_rejects_absolute_and_parent_paths(self) -> None:
        with self.assertRaises(ValueError):
            tool.read_file("research_os_flutter", "../secret.dart")
        with self.assertRaises(ValueError):
            tool.read_file("research_os_flutter", "/secret.dart")

    def test_preview_is_sha_bound(self) -> None:
        current = tool.read_file("research_os_flutter", "lib/main.dart")
        preview = tool.preview("research_os_flutter", "lib/main.dart", current["sha256"], "void main() { print(1); }\n")
        self.assertTrue(preview["changed"])
        self.assertIn("+void main()", preview["diff"])

    @patch("flutter_code_tool.validate", return_value={"ok": True, "steps": []})
    def test_apply_requires_owner_and_validates(self, validate) -> None:
        current = tool.read_file("research_os_flutter", "lib/main.dart")
        result = tool.apply("research_os_flutter", "lib/main.dart", current["sha256"], "void main() { print(1); }\n", "owner@example.com")
        self.assertTrue(result["applied"])
        validate.assert_called_once()

    @patch("flutter_code_tool.validate", return_value={"ok": True, "steps": []})
    def test_email_allowlist_is_not_ignored_when_owner_ids_are_configured(self, validate) -> None:
        current = tool.read_file("research_os_flutter", "lib/main.dart")
        with patch.dict(os.environ, {
            "RESEARCH_OS_CODE_OWNER_IDS": "owner-id-123",
            "RESEARCH_OS_OWNER_EMAILS": "owner@example.com,second-owner@example.com",
        }):
            result = tool.apply(
                "research_os_flutter",
                "lib/main.dart",
                current["sha256"],
                "void main() { print(2); }\n",
                "second-owner@example.com",
            )
        self.assertTrue(result["applied"])
        validate.assert_called_once()

    def test_non_owner_cannot_apply(self) -> None:
        current = tool.read_file("research_os_flutter", "lib/main.dart")
        with self.assertRaises(PermissionError):
            tool.apply("research_os_flutter", "lib/main.dart", current["sha256"], "x\n", "dev@example.com")



    def test_read_normalizes_newlines_but_hashes_raw_bytes(self) -> None:
        path = self.root / "apps" / "research_os_flutter" / "lib" / "main.dart"
        raw = b"void main() {}\r\n"
        path.write_bytes(raw)

        payload = tool.read_file("research_os_flutter", "lib/main.dart")

        self.assertEqual(payload["content"], "void main() {}\n")
        self.assertEqual(payload["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(payload["bytes"], len(raw))

    @patch("flutter_code_tool.validate", return_value={"ok": True, "steps": []})
    def test_apply_rejects_newline_only_change_after_read(self, validate) -> None:
        path = self.root / "apps" / "research_os_flutter" / "lib" / "main.dart"
        path.write_bytes(b"void main() {}\r\n")
        current = tool.read_file("research_os_flutter", "lib/main.dart")

        # Same displayed text, different on-disk bytes.
        path.write_bytes(b"void main() {}\n")

        with self.assertRaisesRegex(RuntimeError, "file changed"):
            tool.apply(
                "research_os_flutter",
                "lib/main.dart",
                current["sha256"],
                "void main() { print(3); }\n",
                "owner@example.com",
            )
        validate.assert_not_called()

    @patch("flutter_code_tool.validate", return_value={"ok": False, "steps": [{"exit_code": 1}]})
    def test_failed_validation_restores_original_bytes_exactly(self, validate) -> None:
        path = self.root / "apps" / "research_os_flutter" / "lib" / "main.dart"
        original = b"void main() {}\r\n"
        path.write_bytes(original)
        current = tool.read_file("research_os_flutter", "lib/main.dart")

        result = tool.apply(
            "research_os_flutter",
            "lib/main.dart",
            current["sha256"],
            "void main() { print(4); }\n",
            "owner@example.com",
        )

        self.assertFalse(result["applied"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
        validate.assert_called_once()

        import json
        evidence = json.loads(Path(result["evidence"]).read_text(encoding="utf-8"))
        self.assertTrue(evidence["rolled_back"])
        self.assertEqual(evidence["before_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(evidence["final_sha256"], hashlib.sha256(original).hexdigest())


    def test_successful_validation_does_not_report_applied_after_external_change(self) -> None:
        path = self.root / "apps" / "research_os_flutter" / "lib" / "main.dart"
        original = b"void main() {}\r\n"
        external = b"// external edit must survive\n"
        path.write_bytes(original)
        current = tool.read_file("research_os_flutter", "lib/main.dart")

        def validation_with_external_edit(_project_name):
            path.write_bytes(external)
            return {"ok": True, "steps": []}

        with patch("flutter_code_tool.validate", side_effect=validation_with_external_edit):
            result = tool.apply(
                "research_os_flutter",
                "lib/main.dart",
                current["sha256"],
                "void main() { print(2); }\n",
                "owner@example.com",
            )

        self.assertFalse(result["applied"])
        self.assertTrue(result["rollback_conflict"])
        self.assertEqual(path.read_bytes(), external)
        self.assertEqual(result["sha256"], hashlib.sha256(external).hexdigest())
    def test_failed_validation_preserves_external_change(self) -> None:
        path = self.root / "apps" / "research_os_flutter" / "lib" / "main.dart"
        original = b"void main() {}\r\n"
        external = b"// external edit must survive\n"
        path.write_bytes(original)
        current = tool.read_file("research_os_flutter", "lib/main.dart")

        def validation_with_external_edit(_project_name):
            path.write_bytes(external)
            return {"ok": False, "steps": [{"exit_code": 1}]}

        with patch("flutter_code_tool.validate", side_effect=validation_with_external_edit):
            result = tool.apply(
                "research_os_flutter",
                "lib/main.dart",
                current["sha256"],
                "void main() { print(5); }\n",
                "owner@example.com",
            )

        self.assertFalse(result["applied"])
        self.assertFalse(result["rolled_back"])
        self.assertTrue(result["rollback_conflict"])
        self.assertEqual(path.read_bytes(), external)
        self.assertEqual(result["sha256"], hashlib.sha256(external).hexdigest())

        import json
        evidence = json.loads(
            Path(result["evidence"]).read_text(encoding="utf-8")
        )
        self.assertTrue(evidence["rollback_conflict"])
        self.assertEqual(
            evidence["final_sha256"], hashlib.sha256(external).hexdigest()
        )

if __name__ == "__main__":
    unittest.main()
