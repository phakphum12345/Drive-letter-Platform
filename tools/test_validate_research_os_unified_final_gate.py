import unittest
from pathlib import Path
import subprocess
import sys


class UnifiedFinalGateValidatorTest(unittest.TestCase):
    def test_release_decision_requires_source_integrity_and_ci_lite(self) -> None:
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github" / "workflows" / "research-os-unified-final-gate.yml").read_text(encoding="utf-8")
        self.assertIn("CI_LITE: ${{ needs.ci_lite.result }}", workflow)
        self.assertIn('test "$CI_LITE" = success', workflow)
        self.assertIn("ci_lite, flutter_surface, python_surface, laravel_surface", workflow)
        for relative_path in (
            ".github/workflows/research-os-unified-final-gate.yml",
            ".github/workflows/research-os-final-gate.yml",
            ".github/workflows/final-gate.yml",
            ".github/workflows/research-os-unified-10x10-gate.yml",
        ):
            gate = (root / relative_path).read_text(encoding="utf-8")
            self.assertIn("python tools/m2_source_integrity_audit.py", gate, relative_path)

    def test_validator_passes_on_current_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "tools" / "validate_research_os_unified_final_gate.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UNIFIED_FINAL_GATE_CONTRACT=PASS", result.stdout)
        self.assertIn("AEOS_RECHECK=BOUND_TO_FINAL_GATE", result.stdout)
        self.assertIn("AEOS_RELEASE_AUTHORITY=FINAL_GATE", result.stdout)
        self.assertIn("RUNTIME_RESOLUTION=BOUND_TO_PLATFORM", result.stdout)


if __name__ == "__main__":
    unittest.main()
