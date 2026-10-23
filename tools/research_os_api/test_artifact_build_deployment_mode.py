from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "artifacts-build.yml"


class ArtifactDeploymentModeTests(unittest.TestCase):
    def test_mode_switch_and_endpoints_are_declared(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("deployment_mode:", text)
        self.assertIn("          - local\n          - render", text)
        self.assertIn("default: local", text)
        self.assertIn("https://research-os-api-phakphoum.onrender.com", text)
        self.assertIn("http://127.0.0.1:8787", text)

    def test_all_flutter_targets_use_the_selected_endpoint(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('flutter build web --release --dart-define=RESEARCH_OS_API_BASE_URL="$API_BASE_URL"', text)
        self.assertIn('flutter build windows --release --dart-define=RESEARCH_OS_API_BASE_URL="$env:API_BASE_URL"', text)
        self.assertIn('flutter build ios --release --no-codesign --dart-define=RESEARCH_OS_API_BASE_URL="$API_BASE_URL"', text)

    def test_manifests_bind_mode_endpoint_and_target_sha(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"deployment_mode":os.environ["DEPLOYMENT_MODE"]', text)
        self.assertIn('"api_base_default":os.environ["API_BASE_URL"]', text)
        self.assertIn('deployment_mode = $env:DEPLOYMENT_MODE', text)
        self.assertIn('api_base_default = $env:API_BASE_URL', text)
        self.assertIn("artifacts-ios/deployment-manifest.json", text)
        self.assertIn("deployment-manifest.json", text)
        self.assertIn("SHA256SUMS.txt", text)


if __name__ == "__main__":
    unittest.main()
