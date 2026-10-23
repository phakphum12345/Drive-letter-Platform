"""Tests for Phase E unified Windows distribution governance."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tools import validate_phase_e_unified_windows_distribution as validator


class PhaseEUnifiedWindowsDistributionTests(unittest.TestCase):
    def test_contract_reconciles(self) -> None:
        self.assertEqual((), validator.validate())

    def test_installer_e2e_is_bound(self) -> None:
        workflow = validator._read_phase_e_workflow(validator.ROOT)
        self.assertIn("Installer install run uninstall E2E", workflow)
        self.assertIn("WINDOWS_INSTALL_E2E_EVIDENCE.json", workflow)

    def test_installer_e2e_requires_uninstall(self) -> None:
        original = validator.json.loads(
            validator.CONTRACT.read_text(encoding="utf-8")
        )
        original["install_e2e"]["uninstall_required"] = False
        with patch.object(validator, "json") as mocked_json:
            mocked_json.loads.return_value = original
            self.assertIn(
                "installer E2E invariant missing: uninstall_required",
                validator.validate(),
            )

    def test_distribution_cannot_replace_release_authority(self) -> None:
        original = validator.json.loads(
            validator.CONTRACT.read_text(encoding="utf-8")
        )
        original["authority"]["final_gate_remains_release_authority"] = False
        with patch.object(validator, "json") as mocked_json:
            mocked_json.loads.return_value = original
            self.assertIn(
                "authority invariant missing: final_gate_remains_release_authority",
                validator.validate(),
            )

    def test_uninstall_run_uses_native_powershell_and_unique_ids(self) -> None:
        installer = (
            validator.ROOT
            / "owner_special/installer/owner-special-platform.iss"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'Filename: "{sys}\\WindowsPowerShell\\v1.0\\powershell.exe"',
            installer,
        )
        self.assertIn(
            'Flags: 64bit runhidden waituntilterminated; '
            'RunOnceId: "ResearchOSOwnerFriendServiceUninstall"',
            installer,
        )
        self.assertIn(
            'Flags: 64bit runhidden waituntilterminated; '
            'RunOnceId: "ResearchOSServiceUninstall"',
            installer,
        )
    def test_windows_service_uses_canonical_api_entrypoint(self) -> None:
        source = (
            validator.ROOT
            / "tools"
            / "research_os_service"
            / "Program.cs"
        ).read_text(encoding="utf-8")

        self.assertIn("server.py", source)
        self.assertNotIn("render_server.py", source)

    def test_installer_e2e_runs_for_relevant_pull_requests(self) -> None:
        workflow = validator._read_phase_e_workflow(validator.ROOT)
        self.assertIn("  pull_request:", workflow)
        self.assertIn("      - main", workflow)
        self.assertIn('"tools/**"', workflow)

    def test_bundled_api_import_smoke_is_required(self) -> None:
        workflow = validator._read_phase_e_workflow(validator.ROOT)
        self.assertIn("Bundled API import smoke test", workflow)
        self.assertIn("BUNDLED_API_IMPORT=PASS", workflow)
        self.assertIn("import server; print('BUNDLED_API_IMPORT=PASS')", workflow)

    def test_api_readiness_requires_health_and_packaged_ui(self) -> None:
        workflow = validator._read_phase_e_workflow(validator.ROOT)
        self.assertIn("/health", workflow)
        self.assertIn("apiHealth.status -eq 'ok'", workflow)
        self.assertIn("apiHealth.ui -eq $true", workflow)

    def test_service_start_failure_collects_runtime_and_event_diagnostics(self) -> None:
        workflow = validator._read_phase_e_workflow(validator.ROOT)
        self.assertIn("Get-WinEvent", workflow)
        self.assertIn("INSTALLED_API_IMPORT_EXIT=", workflow)
        self.assertIn("Research OS service did not reach Running state after install.", workflow)

    def test_workflow_must_bind_owner_special(self) -> None:
        with patch.object(validator, "_read_phase_e_workflow", return_value=""):
            self.assertIn(
                "Phase E workflow missing required marker: research_os_owner_special.exe",
                validator.validate(),
            )

    def test_final_gate_hook_is_required(self) -> None:
        with patch.object(validator, "_read_unified_final_gate", return_value=""):
            self.assertIn(
                "Unified Final Gate is missing the Phase E distribution test",
                validator.validate(),
            )

    def test_contract_requires_exact_sha(self) -> None:
        original = validator.json.loads(
            validator.CONTRACT.read_text(encoding="utf-8")
        )
        original["provenance"]["source_sha_required"] = False
        with patch.object(validator, "json") as mocked_json:
            mocked_json.loads.return_value = original
            self.assertIn(
                "provenance invariant missing: source_sha_required",
                validator.validate(),
            )


if __name__ == "__main__":
    unittest.main()
