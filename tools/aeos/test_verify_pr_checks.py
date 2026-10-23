import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("verify_pr_checks.py")
SPEC = spec_from_file_location("verify_pr_checks", MODULE_PATH)
VERIFY_PR_CHECKS = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(VERIFY_PR_CHECKS)

classify = VERIFY_PR_CHECKS.classify
normalize_check_run = VERIFY_PR_CHECKS.normalize_check_run
normalize_status_context = VERIFY_PR_CHECKS.normalize_status_context
poll_interval = VERIFY_PR_CHECKS.poll_interval
current_pr_head = VERIFY_PR_CHECKS.current_pr_head


class VerifyPrChecksTests(unittest.TestCase):
    def test_self_check_run_is_excluded_by_run_url(self):
        self.assertIsNone(normalize_check_run({"name":"comprehensive-review","status":"in_progress","details_url":"https://github.com/o/r/actions/runs/123/job/456"}, "123"))

    def test_self_check_run_is_excluded_by_plain_run_url(self):
        self.assertIsNone(normalize_check_run({"name":"comprehensive-review","status":"completed","conclusion":"success","details_url":"https://github.com/o/r/actions/runs/123"}, "123"))

    def test_prior_aggregator_failure_is_not_external_ci_evidence(self):
        self.assertIsNone(normalize_check_run({"name":"comprehensive-review","status":"completed","conclusion":"failure","details_url":"https://github.com/o/r/actions/runs/999/job/1"}, "123"))

    def test_aggregator_status_context_is_excluded_across_run_ids(self):
        self.assertIsNone(normalize_status_context({"context":"AEOS One-Shot Comprehensive Review","state":"failure","target_url":"https://github.com/o/r/actions/runs/999"}, "123"))

    def test_skipped_check_run_is_unproven_not_passing(self):
        check = normalize_check_run({"name":"build-ios-unsigned-ipa","status":"completed","conclusion":"skipped","details_url":"https://github.com/o/r/actions/runs/999/job/1"}, "123")
        self.assertEqual(check["bucket"], "unproven")
        self.assertEqual(check["state"], "SKIPPED")

    def test_explicitly_non_applicable_push_image_skip_is_reasoned(self):
        check = normalize_check_run({"name":"push-image","status":"completed","conclusion":"skipped","details_url":"https://github.com/o/r/actions/runs/999/job/1"}, "123")
        self.assertEqual(check["bucket"], "not_applicable")
        self.assertIn("only on push", check["reason_code"])

    @patch.object(VERIFY_PR_CHECKS, "paginate_array", return_value=[{"filename":"tools/recover-research-os-runtime.ps1"}])
    @patch.object(VERIFY_PR_CHECKS, "paginate", return_value=[{
        "name":"Decide whether legacy Flutter Windows validation is relevant",
        "run_id":456,"conclusion":"success",
    }])
    @patch.object(VERIFY_PR_CHECKS, "request_json")
    def test_flutter_skip_is_not_applicable_only_with_exact_scope_evidence(self, request, _jobs, _files):
        request.side_effect = [
            ({"name":"Research OS Final Gate","path":".github/workflows/research-os-final-gate.yml",
              "event":"pull_request","head_sha":"abc123","conclusion":"success"}, {}),
            ({"run_id":456,"name":"Flutter Windows build analyze test",
              "status":"completed","conclusion":"skipped"}, {}),
            ({"head":{"sha":"abc123"},"base":{"sha":"base456"}}, {}),
        ]
        check = {"name":"Flutter Windows build analyze test","status":"completed","conclusion":"skipped",
                 "details_url":"https://github.com/o/r/actions/runs/456/job/789"}
        normalized = normalize_check_run(check, "999")
        result = VERIFY_PR_CHECKS.prove_flutter_scope_skip(check, normalized, "o/r", "36", "abc123")
        self.assertEqual(result["bucket"], "not_applicable")
        self.assertIn("all PR files are outside", result["reason_code"])
        self.assertEqual(result["source"], "check_run+exact_scope_evidence")

    @patch.object(VERIFY_PR_CHECKS, "paginate_array", return_value=[{"filename":"v3/flutter_app/lib/main.dart"}])
    @patch.object(VERIFY_PR_CHECKS, "paginate", return_value=[{
        "name":"Decide whether legacy Flutter Windows validation is relevant",
        "run_id":456,"conclusion":"success",
    }])
    @patch.object(VERIFY_PR_CHECKS, "request_json")
    def test_flutter_skip_with_relevant_changed_file_remains_unproven(self, request, _jobs, _files):
        request.side_effect = [
            ({"name":"Research OS Final Gate","path":".github/workflows/research-os-final-gate.yml",
              "event":"pull_request","head_sha":"abc123","conclusion":"success"}, {}),
            ({"run_id":456,"name":"Flutter Windows build analyze test",
              "status":"completed","conclusion":"skipped"}, {}),
            ({"head":{"sha":"abc123"},"base":{"sha":"base456"}}, {}),
        ]
        check = {"name":"Flutter Windows build analyze test","status":"completed","conclusion":"skipped",
                 "details_url":"https://github.com/o/r/actions/runs/456/job/789"}
        normalized = normalize_check_run(check, "999")
        result = VERIFY_PR_CHECKS.prove_flutter_scope_skip(check, normalized, "o/r", "36", "abc123")
        self.assertEqual(result["bucket"], "unproven")

    def test_flutter_skip_without_pull_request_number_remains_unproven(self):
        check = {"name":"Flutter Windows build analyze test","status":"completed","conclusion":"skipped",
                 "details_url":"https://github.com/o/r/actions/runs/456/job/789"}
        normalized = normalize_check_run(check, "999")
        result = VERIFY_PR_CHECKS.prove_flutter_scope_skip(check, normalized, "o/r", "", "abc123")
        self.assertEqual(result["bucket"], "unproven")

    def test_neutral_check_run_is_unproven_not_passing(self):
        check = normalize_check_run({"name":"non-blocking-note","status":"completed","conclusion":"neutral"}, "123")
        self.assertEqual(check["bucket"], "unproven")
        self.assertEqual(check["state"], "NEUTRAL")

    def test_pending_and_failed_checks_are_classified_separately(self):
        pending, bad, unproven = classify([{"source":"check_run","name":"ci","bucket":"pending","state":"IN_PROGRESS"},{"source":"status","name":"lint","bucket":"fail","state":"FAILURE"},{"source":"check_run","name":"optional?","bucket":"unproven","state":"SKIPPED"}])
        self.assertEqual([item["name"] for item in pending], ["ci"])
        self.assertEqual([item["name"] for item in bad], ["lint"])
        self.assertEqual([item["name"] for item in unproven], ["optional?"])

    def test_status_context_can_be_excluded_by_run_url(self):
        self.assertIsNone(normalize_status_context({"context":"AEOS One-Shot Comprehensive Review","state":"pending","target_url":"https://github.com/o/r/actions/runs/123/job/456"}, "123"))

    def test_status_context_can_be_excluded_by_plain_run_url(self):
        self.assertIsNone(normalize_status_context({"context":"AEOS One-Shot Comprehensive Review","state":"pending","target_url":"https://github.com/o/r/actions/runs/123"}, "123"))

    def test_poll_interval_backs_off_and_caps(self):
        self.assertEqual(poll_interval(1, 5, 30), 5)
        self.assertEqual(poll_interval(4, 5, 30), 10)
        self.assertEqual(poll_interval(7, 5, 30), 20)
        self.assertEqual(poll_interval(10, 5, 30), 30)

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({"head":{"sha":"abc123"}}, {}))
    def test_current_pr_head_reads_live_api_identity(self, _request):
        self.assertEqual(current_pr_head("o/r", "390"), "abc123")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({"head":{"sha":""}}, {}))
    def test_current_pr_head_fails_closed_when_missing(self, _request):
        with self.assertRaises(RuntimeError):
            current_pr_head("o/r", "390")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 456,
        "head_sha": "abc123",
        "name": "build",
        "status": "completed",
        "conclusion": "success",
    }, {}))
    def test_stale_pending_check_reconciles_only_matching_completed_job(self, request):
        original = {
            "name": "build",
            "status": "in_progress",
            "conclusion": None,
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "999")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "999"
        )
        self.assertEqual(result["bucket"], "pass")
        self.assertEqual(result["state"], "SUCCESS")
        self.assertEqual(result["source"], "check_run+actions_job")
        request.assert_called_once_with("https://api.github.com/repos/o/r/actions/jobs/789")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 456,
        "head_sha": "different-sha",
        "name": "build",
        "status": "completed",
        "conclusion": "success",
    }, {}))
    def test_stale_pending_check_does_not_accept_different_job_sha(self, _request):
        original = {
            "name": "build",
            "status": "in_progress",
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "999")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "999"
        )
        self.assertEqual(result["bucket"], "pending")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 456,
        "head_sha": "abc123",
        "name": "build",
        "status": "completed",
        "conclusion": "failure",
    }, {}))
    def test_stale_pending_check_preserves_real_job_failure(self, _request):
        original = {
            "name": "build",
            "status": "in_progress",
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "999")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "999"
        )
        self.assertEqual(result["bucket"], "fail")
        self.assertEqual(result["state"], "FAILURE")

    @patch.object(VERIFY_PR_CHECKS, "request_json")
    def test_pending_check_with_untrusted_url_is_not_reconciled(self, request):
        original = {
            "name": "build",
            "status": "in_progress",
            "head_sha": "abc123",
            "details_url": "https://example.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "999")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "999"
        )
        self.assertEqual(result["bucket"], "pending")
        request.assert_not_called()



    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 999,
        "head_sha": "abc123",
        "name": "build",
        "status": "completed",
        "conclusion": "success",
    }, {}))
    def test_stale_pending_check_does_not_accept_different_run_id(self, _request):
        original = {
            "name": "build",
            "status": "in_progress",
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "1000")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "1000"
        )
        self.assertEqual(result["bucket"], "pending")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 456,
        "head_sha": "abc123",
        "name": "build",
        "status": "in_progress",
        "conclusion": None,
    }, {}))
    def test_matching_but_running_job_remains_pending(self, _request):
        original = {
            "name": "build",
            "status": "in_progress",
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        normalized = normalize_check_run(original, "1000")
        result = VERIFY_PR_CHECKS.reconcile_pending_job_check(
            original, normalized, "o/r", "abc123", "1000"
        )
        self.assertEqual(result["bucket"], "pending")

    @patch.object(VERIFY_PR_CHECKS, "request_json", return_value=({
        "run_id": 456,
        "head_sha": "abc123",
        "name": "build",
        "status": "completed",
        "conclusion": "success",
    }, {}))
    @patch.object(VERIFY_PR_CHECKS, "paginate")
    def test_fetch_external_checks_integrates_exact_job_reconciliation(self, paginate, _request):
        check_run = {
            "name": "build",
            "status": "in_progress",
            "conclusion": None,
            "head_sha": "abc123",
            "details_url": "https://github.com/o/r/actions/runs/456/job/789",
        }
        paginate.side_effect = [[check_run], []]
        result = VERIFY_PR_CHECKS.fetch_external_checks("o/r", "abc123", "1000")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["bucket"], "pass")
        self.assertEqual(result[0]["source"], "check_run+actions_job")


if __name__ == "__main__":
    unittest.main()