import unittest

from tools.validate_generate_orchestrator import (
    WORKFLOWS,
    unsupported_required_inputs,
    workflow_dispatch_inputs,
)


class GenerateOrchestratorInputTests(unittest.TestCase):
    def test_required_choice_with_default_is_supported(self):
        self.assertEqual(
            unsupported_required_inputs({
                "deployment_mode": {
                    "description": "API endpoint profile",
                    "required": True,
                    "type": "choice",
                    "options": ["local", "render"],
                    "default": "local",
                }
            }),
            [],
        )

    def test_artifact_build_default_is_supported_and_orchestrator_passes_it(self):
        schema = workflow_dispatch_inputs(WORKFLOWS / "artifacts-build.yml")
        self.assertEqual(schema["deployment_mode"]["default"], "local")
        self.assertEqual(unsupported_required_inputs(schema), [])
        source = (WORKFLOWS / "generate-orchestrator.yml").read_text(encoding="utf-8")
        self.assertIn('elif isinstance(spec, dict) and spec.get("required") is True and "default" in spec:', source)
        self.assertIn('inputs[name] = spec["default"]', source)

    def test_required_unknown_input_without_default_stays_blocking(self):
        self.assertEqual(
            unsupported_required_inputs({
                "unrecognized_required_input": {"required": True, "type": "string"}
            }),
            ["unrecognized_required_input"],
        )

    def test_orchestrator_supported_required_inputs_remain_supported(self):
        self.assertEqual(
            unsupported_required_inputs({"target_sha": {"required": True, "type": "string"}}),
            [],
        )

    def test_artifact_upload_actions_are_pinned_to_full_commit_shas(self):
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for relative in (
            ".github/workflows/final-gate.yml",
            ".github/workflows/generate-orchestrator.yml",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            refs = re.findall(r"uses:\s*actions/upload-artifact@([^\s#]+)", source)
            self.assertTrue(refs, f"{relative} must declare its artifact upload action")
            for ref in refs:
                self.assertRegex(
                    ref,
                    r"^[0-9a-f]{40}$",
                    f"{relative} has an unpinned artifact upload action ref: {ref}",
                )


if __name__ == "__main__":
    unittest.main()
