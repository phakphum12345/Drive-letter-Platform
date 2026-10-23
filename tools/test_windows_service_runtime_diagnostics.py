from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "diagnose_windows_service_runtime.ps1"


class WindowsServiceRuntimeDiagnosticsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_diagnostic_script_exists_and_declares_versioned_evidence_contract(self) -> None:
        self.assertIn("research-os.windows-service-diagnostics/v1", self.source)
        self.assertIn("COLLECTED_NOT_CERTIFIED", self.source)
        self.assertIn("read_only = $true", self.source)

    def test_collects_service_process_socket_http_log_and_event_evidence(self) -> None:
        for marker in (
            "Win32_Service",
            "Win32_Process",
            "Get-NetTCPConnection",
            "research_os_api_health",
            "owner_friend_health",
            "Get-Content -LiteralPath $file.FullName -Tail $LogTailLines",
            "Get-WinEvent",
            "parent_process_id",
            "command_line",
            "SHARED_RUNTIME_IN_USE",
            "service_process_ownership",
            "SERVICE_PID_NOT_IN_INVENTORY",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.source)

    def test_owner_friend_cleanup_scopes_processes_to_exact_entrypoint(self) -> None:
        installer = (
            ROOT.parent
            / "owner_special"
            / "scripts"
            / "install-owner-service.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("run_friend_service.py", installer)
        self.assertIn("CommandLine.IndexOf($entrypoint", installer)
        self.assertIn("[StringComparison]::OrdinalIgnoreCase", installer)
        self.assertIn(
            "The bundled interpreter is shared by API and Owner Friend",
            installer,
        )
        # A shared python.exe path must never be the sole process selector.
        self.assertNotIn(
            "return @(" + "Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {\n"
            "        $_.Name -ieq 'python.exe' -and $_.ExecutablePath -and\n"
            "        ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $pythonPath)\n"
            "    })",
            installer,
        )

    def test_windows_installer_e2e_proves_api_stability_during_owner_friend_lifecycle(self) -> None:
        workflow = (
            ROOT.parent
            / ".github"
            / "workflows"
            / "research-os-phase-e-unified-windows-distribution.yml"
        ).read_text(encoding="utf-8")

        for marker in (
            "ResearchOSService",
            "$apiPidBefore",
            "Start-Job -ArgumentList $apiPidBefore",
            "API_SERVICE_PID_OR_STATE_CHANGED",
            "API_HEALTH_PROBE_FAILED",
            "install-owner-service.ps1",
            "-Action uninstall -Root $installRoot",
            "-Action install -Root $installRoot",
            "$checks['owner_friend_lifecycle_api_pid_stable'] = $true",
            "$checks['owner_friend_lifecycle_api_health_continuous'] = $true",
            "OWNER_FRIEND_LIFECYCLE_API_STABILITY=PASS",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, workflow)

        self.assertIn("Receive-Job -Job $monitor", workflow)
        self.assertIn("ResearchOSOwnerFriendService", workflow)

    def test_collector_does_not_stop_processes_or_mutate_services(self) -> None:
        forbidden = (
            "Stop-Process",
            "Stop-Service",
            "Start-Service",
            "Restart-Service",
            "Remove-Service",
            "sc.exe delete",
            "Set-Service",
            "New-Service",
            "Win32_Process).Terminate",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker.lower(), self.source.lower())

    def test_process_command_line_redacts_common_inline_credentials(self) -> None:
        self.assertIn("Protect-CommandLine", self.source)
        self.assertIn("<REDACTED>", self.source)
        self.assertNotIn("Get-ChildItem Env:", self.source)
        self.assertNotIn("Get-Item Env:", self.source)

    def test_optional_output_path_is_explicit_and_report_does_not_claim_pass(self) -> None:
        self.assertIn("if ($OutputPath)", self.source)
        self.assertIn("DIAGNOSTIC_STATUS=COLLECTED_NOT_CERTIFIED", self.source)
        self.assertNotIn("FINAL_GATE=PASS", self.source)
        self.assertNotIn("RELEASE_CERTIFIED=TRUE", self.source)



class WindowsServiceRuntimeAutoRecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.recovery = (ROOT / "recover-research-os-runtime.ps1").read_text(encoding="utf-8")
        cls.service_host = (ROOT / "research_os_service" / "Program.cs").read_text(encoding="utf-8")

    def test_deep_recovery_does_not_block_initial_api_startup(self) -> None:
        recovery_call = "RunRuntimeRecovery(repoRoot, dataDir, _logger);"
        self.assertEqual(self.service_host.count(recovery_call), 1)
        self.assertLess(
            self.service_host.index("if (!_process.Start())"),
            self.service_host.index("await exitTask;"),
        )
        self.assertLess(
            self.service_host.index("await exitTask;"),
            self.service_host.index(recovery_call),
        )
        self.assertIn("child has exited", self.service_host)
        self.assertIn("existing SCM service restart", self.service_host)
        self.assertIn("recovery.ExitCode != 0", self.service_host)
        self.assertIn("API startup is blocked", self.service_host)

    def test_recovery_requires_source_bound_zip_and_manifest_hashes(self) -> None:
        for marker in (
            "OWNER_SPECIAL_PLATFORM_INSTALL_PROVENANCE.json",
            "platform_zip_sha256",
            "distribution_manifest_sha256",
            "DISTRIBUTION_MANIFEST.json",
            "DISTRIBUTION_MANIFEST.sha256",
            "Get-Sha256 $zipPath",
            "RECOVERY_BLOCKED",
            "source_sha",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.recovery)

    def test_recovery_is_runtime_only_and_fail_closed(self) -> None:
        for marker in (
            "'runtime/python/'",
            "'tools/'",
            "'v3/'",
            "'current/'",
            "'platform/'",
            "runtime-recovery-attempt.json",
            "a previous recovery attempt",
            "no process was stopped",
            "user_data_modified = $false",
            "Get-CimInstance Win32_Process",
            "post-repair verification failed",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.recovery)
        self.assertNotIn("Expand-Archive", self.recovery)
        self.assertNotIn("Stop-Process", self.recovery)
        self.assertNotIn("Stop-Service", self.recovery)
        self.assertNotIn("sc.exe delete", self.recovery)

if __name__ == "__main__":
    unittest.main()
