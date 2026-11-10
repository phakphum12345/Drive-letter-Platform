from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "static.yml"


class PagesDeploymentContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_builds_from_canonical_research_os_repository(self):
        self.assertIn("repository: phakphum12345/Drive-letter", self.workflow)
        self.assertIn("path: source", self.workflow)
        self.assertIn("source/apps/research_os_flutter", self.workflow)
        self.assertIn("flutter build web --release", self.workflow)

    def test_compiles_the_render_api_endpoint_and_pages_base_path(self):
        self.assertIn(
            "https://research-os-api-phakphoum-v0wf.onrender.com",
            self.workflow,
        )
        self.assertIn('--base-href "/Drive-letter-Platform/"', self.workflow)
        self.assertIn(
            "--dart-define=RESEARCH_OS_API_BASE_URL=",
            self.workflow,
        )

    def test_legacy_web_is_preserved_as_compatibility_not_primary_ui(self):
        self.assertIn(
            "source/apps/research_os_web/. site/compatibility/research_os_web/",
            self.workflow,
        )
        self.assertIn('"role": "legacy-compatibility-only"', self.workflow)
        self.assertIn("test -s site/index.html", self.workflow)

    def test_pull_requests_validate_without_deploying_production_pages(self):
        self.assertIn("pull_request:", self.workflow)
        self.assertIn(
            "if: ${{ github.event_name != 'pull_request' }}",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
