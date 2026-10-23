"""Regression tests preventing unrelated PRs from cancelling Recon evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
WORKFLOWS = ROOT.parent / ".github" / "workflows"


class ReconConcurrencyContractTests(unittest.TestCase):
    def test_recon_concurrency_is_scoped_to_pr_or_ref(self):
        source = (WORKFLOWS / "recon-continuous-reconciliation.yml").read_text(encoding="utf-8")
        self.assertIn(
            "group: recon-continuous-reconciliation-${{ github.event.pull_request.number || github.ref }}",
            source,
        )
        self.assertIn("cancel-in-progress: false", source)

    def test_100project_concurrency_is_scoped_to_pr_or_ref(self):
        source = (WORKFLOWS / "github-100project-continuous-assurance.yml").read_text(encoding="utf-8")
        self.assertIn(
            "group: github-100project-assurance-${{ github.event.pull_request.number || github.ref }}",
            source,
        )
        self.assertIn("cancel-in-progress: false", source)

    def test_recon_and_100project_do_not_share_a_global_group(self):
        recon = (WORKFLOWS / "recon-continuous-reconciliation.yml").read_text(encoding="utf-8")
        assurance = (WORKFLOWS / "github-100project-continuous-assurance.yml").read_text(encoding="utf-8")
        self.assertNotEqual(
            recon.split("group:", 1)[1].splitlines()[0].strip(),
            assurance.split("group:", 1)[1].splitlines()[0].strip(),
        )


if __name__ == "__main__":
    unittest.main()
