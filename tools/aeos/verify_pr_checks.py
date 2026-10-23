#!/usr/bin/env python3
"""Verify that all non-self PR checks for an exact HEAD are terminal and green."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PASS_CONCLUSIONS = {"success"}
UNPROVEN_CONCLUSIONS = {"neutral", "skipped"}
# Explicitly non-required check contract. The trusted main workflow defines
# push-image with `if: event_name == push && registry credentials available`,
# so its skip on pull_request is intentional and non-certifying.
NOT_APPLICABLE_SKIPPED_CHECKS = {
    "push-image": "NOT_APPLICABLE: publish step runs only on push when registry credentials are available",
}
PENDING_STATUSES = {"queued", "in_progress", "pending", "requested", "waiting"}
TRANSIENT_HTTP_STATUS = {429, 500, 502, 503, 504}


def headers() -> dict[str, str]:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    result = {"Accept":"application/vnd.github+json","User-Agent":"aeos-pr-check-verifier","X-GitHub-Api-Version":"2022-11-28"}
    if token:
        result["Authorization"] = "Bearer " + token
    return result


def permission_hint(url: str) -> str | None:
    if "/check-runs" in url:
        return "ensure the workflow token has checks: read permission"
    if "/status" in url:
        return "ensure the workflow token has statuses: read permission"
    return None


def request_json(url: str, *, retries: int = 3, timeout: int = 20) -> tuple[Any, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8")), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            hint = permission_hint(url)
            if exc.code in TRANSIENT_HTTP_STATUS and attempt < retries:
                time.sleep(attempt)
                last_error = RuntimeError(f"transient GitHub HTTP {exc.code}: {body[:300]}")
                continue
            if exc.code == 403 and hint:
                raise RuntimeError(f"GitHub HTTP 403: {hint}. Response: {body[:300]}") from exc
            raise RuntimeError(f"GitHub HTTP {exc.code}: {body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < retries:
                time.sleep(attempt)
                last_error = exc
                continue
            raise RuntimeError(f"GitHub request failed: {exc}") from exc
    raise RuntimeError(f"GitHub request failed after retries: {last_error}")


def paginate(url: str, item_key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        payload, response_headers = request_json(next_url)
        if not isinstance(payload, dict):
            raise RuntimeError(f"GitHub returned invalid payload for {item_key}")
        page_items = payload.get(item_key, [])
        if not isinstance(page_items, list):
            raise RuntimeError(f"GitHub returned invalid {item_key} collection")
        items.extend(item for item in page_items if isinstance(item, dict))
        next_url = None
        for part in response_headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                start, end = part.find("<"), part.find(">", part.find("<") + 1)
                if start != -1 and end != -1:
                    next_url = part[start + 1:end]
                    break
    return items


def paginate_array(url: str) -> list[dict[str, Any]]:
    """Paginate GitHub endpoints that return a JSON array rather than an object."""
    items: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        payload, response_headers = request_json(next_url)
        if not isinstance(payload, list):
            raise RuntimeError("GitHub returned invalid array payload")
        items.extend(item for item in payload if isinstance(item, dict))
        next_url = None
        for part in response_headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                start, end = part.find("<"), part.find(">", part.find("<") + 1)
                if start != -1 and end != -1:
                    next_url = part[start + 1:end]
                    break
    return items


def current_pr_head(repository: str, pr_number: str) -> str:
    repo_path = urllib.parse.quote(repository, safe="/")
    pr_path = urllib.parse.quote(str(pr_number), safe="")
    payload, _ = request_json(f"https://api.github.com/repos/{repo_path}/pulls/{pr_path}")
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned invalid pull request payload")
    head = payload.get("head")
    if not isinstance(head, dict) or not isinstance(head.get("sha"), str) or not head["sha"]:
        raise RuntimeError("GitHub pull request has no valid head SHA")
    return head["sha"]


def is_self_check(check: dict[str, Any], current_run_id: str) -> bool:
    """Exclude this aggregator from its own evidence, including prior retry runs."""
    url = str(check.get("details_url") or check.get("html_url") or check.get("target_url") or "")
    if current_run_id and re.search(rf"/actions/runs/{re.escape(current_run_id)}(?:$|[/?#])", url):
        return True
    # Previous runs of this meta-workflow can be red because their wait budget
    # expired. They are not source checks and must not poison a later resumed run.
    name = str(check.get("name") or check.get("context") or "").strip().casefold()
    return name in {"comprehensive-review", "aeos one-shot comprehensive review"}


def normalize_check_run(check: dict[str, Any], current_run_id: str) -> dict[str, Any] | None:
    if is_self_check(check, current_run_id):
        return None
    status = str(check.get("status") or "").lower()
    conclusion = str(check.get("conclusion") or "").lower()
    name = str(check.get("name") or "").strip()
    reason_code = None
    if status != "completed":
        bucket, state = "pending", status.upper() or "UNKNOWN"
    elif conclusion in PASS_CONCLUSIONS:
        bucket, state = "pass", conclusion.upper()
    elif conclusion == "skipped" and name in NOT_APPLICABLE_SKIPPED_CHECKS:
        bucket, state = "not_applicable", conclusion.upper()
        reason_code = NOT_APPLICABLE_SKIPPED_CHECKS[name]
    elif conclusion in UNPROVEN_CONCLUSIONS:
        bucket, state = "unproven", conclusion.upper()
    else:
        bucket, state = "fail", conclusion.upper() or "FAILED"
    return {"source":"check_run","name":name,"bucket":bucket,"state":state,"reason_code":reason_code,"details_url":check.get("details_url") or check.get("html_url")}


def normalize_status_context(status: dict[str, Any], current_run_id: str) -> dict[str, Any] | None:
    if is_self_check(status, current_run_id):
        return None
    state = str(status.get("state") or "").lower()
    if state == "success":
        bucket = "pass"
    elif state in PENDING_STATUSES:
        bucket = "pending"
    else:
        bucket = "fail"
    return {"source":"status","name":status.get("context"),"bucket":bucket,"state":state.upper() or "UNKNOWN","details_url":status.get("target_url")}


def summarize(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source":c.get("source"),"name":c.get("name"),"state":c.get("state"),"bucket":c.get("bucket"),"reason_code":c.get("reason_code"),"details_url":c.get("details_url")} for c in checks]


def classify(checks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate running checks, proven failures, and terminal-but-unproven checks."""
    return (
        [c for c in checks if c.get("bucket") == "pending"],
        [c for c in checks if c.get("bucket") == "fail"],
        [c for c in checks if c.get("bucket") == "unproven"],
    )


def reconcile_pending_job_check(
    check: dict[str, Any],
    normalized: dict[str, Any],
    repository: str,
    expected_head_sha: str,
    current_run_id: str,
) -> dict[str, Any]:
    """Reconcile a stale pending check-run using its exact GitHub Actions job.

    Only trust the job endpoint when the URL belongs to this repository and
    both the job's run ID and HEAD SHA match the identity encoded by the check.
    If any identity field is absent or mismatched, retain the original pending
    verdict; never infer success from a similarly named or unrelated job.
    """
    if normalized.get("bucket") != "pending":
        return normalized
    details_url = str(check.get("details_url") or check.get("html_url") or "")
    match = re.fullmatch(
        rf"/{re.escape(repository)}/actions/runs/([0-9]+)/job/([0-9]+)/?",
        urllib.parse.urlparse(details_url).path,
    )
    parsed = urllib.parse.urlparse(details_url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com" or not match:
        return normalized

    run_id, job_id = match.groups()
    check_sha = check.get("head_sha")
    if not isinstance(check_sha, str) or check_sha != expected_head_sha:
        return normalized

    repo_path = urllib.parse.quote(repository, safe="/")
    job, _ = request_json(f"https://api.github.com/repos/{repo_path}/actions/jobs/{job_id}")
    if not isinstance(job, dict):
        raise RuntimeError("GitHub returned invalid Actions job payload")
    if str(job.get("run_id") or "") != run_id:
        return normalized
    if job.get("head_sha") != expected_head_sha:
        return normalized
    if str(job.get("name") or "").strip() != str(check.get("name") or "").strip():
        return normalized

    job_status = str(job.get("status") or "").lower()
    if job_status != "completed":
        return normalized
    reconciled = normalize_check_run(
        {
            "name": check.get("name"),
            "status": job_status,
            "conclusion": job.get("conclusion"),
            "details_url": details_url,
            "head_sha": job.get("head_sha"),
        },
        current_run_id,
    )
    # The original check was already established as external. A job endpoint
    # result for this exact run/job/SHA is authoritative for its terminal state.
    if reconciled is None:
        return normalized
    reconciled["source"] = "check_run+actions_job"
    reconciled["reason_code"] = "RECONCILED_EXACT_ACTIONS_JOB"
    return reconciled


def prove_flutter_scope_skip(
    check: dict[str, Any],
    normalized: dict[str, Any],
    repository: str,
    pr_number: str,
    expected_head_sha: str,
) -> dict[str, Any]:
    """Mark Flutter skipped as non-applicable only with exact-SHA scope evidence.

    Fail closed unless the skipped check belongs to a successful pull_request run
    of the trusted Research OS Final Gate workflow, the exact Flutter job really
    completed as skipped, the scope-decision job succeeded, and every changed PR
    file is outside the workflow's declared Flutter validation paths.
    """
    if not (
        normalized.get("bucket") == "unproven"
        and normalized.get("state") == "SKIPPED"
        and str(check.get("name") or "").strip() == "Flutter Windows build analyze test"
    ):
        return normalized
    if not pr_number:
        return normalized

    details_url = str(check.get("details_url") or check.get("html_url") or "")
    parsed = urllib.parse.urlparse(details_url)
    match = re.fullmatch(
        rf"/{re.escape(repository)}/actions/runs/([0-9]+)/job/([0-9]+)/?",
        parsed.path,
    )
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com" or not match:
        return normalized
    run_id, job_id = match.groups()
    repo_path = urllib.parse.quote(repository, safe="/")
    run, _ = request_json(f"https://api.github.com/repos/{repo_path}/actions/runs/{run_id}")
    if not isinstance(run, dict):
        return normalized
    if (
        run.get("name") != "Research OS Final Gate"
        or run.get("path") != ".github/workflows/research-os-final-gate.yml"
        or run.get("event") != "pull_request"
        or run.get("head_sha") != expected_head_sha
        or run.get("conclusion") != "success"
    ):
        return normalized

    skipped_job, _ = request_json(f"https://api.github.com/repos/{repo_path}/actions/jobs/{job_id}")
    if not isinstance(skipped_job, dict) or (
        str(skipped_job.get("run_id") or "") != run_id
        or str(skipped_job.get("name") or "").strip() != "Flutter Windows build analyze test"
        or skipped_job.get("status") != "completed"
        or skipped_job.get("conclusion") != "skipped"
    ):
        return normalized

    jobs = paginate(f"https://api.github.com/repos/{repo_path}/actions/runs/{run_id}/jobs?per_page=100", "jobs")
    scope_jobs = [
        job for job in jobs
        if job.get("name") == "Decide whether legacy Flutter Windows validation is relevant"
        and str(job.get("run_id") or "") == run_id
    ]
    if len(scope_jobs) != 1 or scope_jobs[0].get("conclusion") != "success":
        return normalized

    pr_path = urllib.parse.quote(str(pr_number), safe="")
    pr, _ = request_json(f"https://api.github.com/repos/{repo_path}/pulls/{pr_path}")
    if not isinstance(pr, dict):
        return normalized
    head = pr.get("head")
    base = pr.get("base")
    if (
        not isinstance(head, dict) or head.get("sha") != expected_head_sha
        or not isinstance(base, dict) or not isinstance(base.get("sha"), str) or not base["sha"]
    ):
        return normalized

    files = paginate_array(
        f"https://api.github.com/repos/{repo_path}/pulls/{pr_path}/files?per_page=100"
    )
    if not files:
        return normalized
    flutter_scope = re.compile(
        r"^(v3/flutter_app/|packages/research_os_contracts/|"
        r"\.github/actions/flutter-setup/|"
        r"\.github/workflows/(research-os-final-gate|v3-candidate|v3-clean-core)\.yml$)"
    )
    changed_names = [str(item.get("filename") or "") for item in files]
    if any(not name or flutter_scope.search(name) for name in changed_names):
        return normalized

    result = dict(normalized)
    result.update({
        "bucket": "not_applicable",
        "reason_code": (
            "NOT_APPLICABLE: exact-SHA Research OS Final Gate passed; "
            "scope job passed and all PR files are outside Flutter validation scope"
        ),
        "source": "check_run+exact_scope_evidence",
    })
    return result


def fetch_external_checks(repository: str, head_sha: str, current_run_id: str, pr_number: str = "") -> list[dict[str, Any]]:
    repo_path = urllib.parse.quote(repository, safe="/")
    ref = urllib.parse.quote(head_sha, safe="")
    check_runs = paginate(f"https://api.github.com/repos/{repo_path}/commits/{ref}/check-runs?per_page=100", "check_runs")
    statuses = paginate(f"https://api.github.com/repos/{repo_path}/commits/{ref}/status?per_page=100", "statuses")
    external: list[dict[str, Any]] = []
    for item in check_runs:
        normalized = normalize_check_run(item, current_run_id)
        if normalized:
            if pr_number:
                normalized = prove_flutter_scope_skip(
                    item, normalized, repository, pr_number, head_sha
                )
            normalized = reconcile_pending_job_check(
                item, normalized, repository, head_sha, current_run_id
            )
            external.append(normalized)
    for item in statuses:
        normalized = normalize_status_context(item, current_run_id)
        if normalized:
            external.append(normalized)
    return external


def poll_interval(attempt: int, initial_seconds: int, max_seconds: int) -> int:
    exponent = min((max(1, attempt) - 1) // 3, 3)
    return min(max_seconds, initial_seconds * (2**exponent))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--initial-poll-seconds", type=int, default=int(os.environ.get("INITIAL_POLL_SECONDS", "5")))
    parser.add_argument("--max-poll-seconds", type=int, default=int(os.environ.get("MAX_POLL_SECONDS", "30")))
    parser.add_argument("--max-wait-seconds", type=int, default=int(os.environ.get("MAX_WAIT_SECONDS", "900")))
    parser.add_argument("--current-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    args = parser.parse_args()
    if not args.repository or not args.pr_number:
        raise SystemExit("repository and pr-number are required")
    if args.initial_poll_seconds < 1 or args.max_poll_seconds < args.initial_poll_seconds:
        raise SystemExit("invalid poll interval configuration")
    if args.max_wait_seconds < 1:
        raise SystemExit("max wait must be positive")

    deadline = time.monotonic() + args.max_wait_seconds
    attempt = 0
    last_signature: str | None = None
    while True:
        attempt += 1
        live_head = current_pr_head(args.repository, args.pr_number)
        if live_head != args.head_sha:
            raise SystemExit(f"PR HEAD changed during verification: expected {args.head_sha}, got {live_head}")
        checks = fetch_external_checks(args.repository, args.head_sha, args.current_run_id, args.pr_number)
        pending, bad, unproven = classify(checks)
        if bad:
            print(json.dumps({"status":"EXTERNAL_CI_FAILED","result_state":"FAIL","failing_checks":summarize(bad)}, indent=2))
            raise SystemExit("one or more external PR checks failed")
        if unproven:
            print(json.dumps({"status":"BLOCKED_EVIDENCE","result_state":"BLOCKED_EVIDENCE","unproven_checks":summarize(unproven)}, indent=2))
            raise SystemExit(3)  # BLOCKED_EVIDENCE; distinct from a proven CI failure.
        if checks and not pending:
            final_head = current_pr_head(args.repository, args.pr_number)
            if final_head != args.head_sha:
                raise SystemExit(f"PR HEAD changed during final verification: expected {args.head_sha}, got {final_head}")
            final_checks = fetch_external_checks(args.repository, args.head_sha, args.current_run_id, args.pr_number)
            final_pending, final_bad, final_unproven = classify(final_checks)
            if final_bad or final_pending or not final_checks:
                continue
            if final_unproven:
                print(json.dumps({"status":"BLOCKED_EVIDENCE","result_state":"BLOCKED_EVIDENCE","unproven_checks":summarize(final_unproven)}, indent=2))
                raise SystemExit(3)  # BLOCKED_EVIDENCE; do not certify this SHA.
            print(json.dumps({"status":"ALL_EXTERNAL_CHECKS_PASS","check_count":len(final_checks),"checks":summarize(final_checks)}, indent=2))
            return 0

        remaining = max(0, int(deadline - time.monotonic()))
        if remaining <= 0:
            payload = {"status":"WAITING_FOR_EXTERNAL_CI" if pending else "WAITING_FOR_EXTERNAL_CI_REGISTRATION","result_state":"RESULT_PENDING","reason_code":"WAIT_BUDGET_EXCEEDED","execution_state":"WAITING","poll":attempt,"pending_count":len(pending),"pending_checks":summarize(pending),"observed_check_count":len(checks)}
            print(json.dumps(payload, indent=2))
            raise SystemExit(2)  # RESULT_PENDING / WAIT_BUDGET_EXCEEDED, not a source-check FAIL.
        payload = {"status":"WAITING_FOR_EXTERNAL_CI" if pending else "WAITING_FOR_EXTERNAL_CI_REGISTRATION","result_state":"RESULT_PENDING","execution_state":"WAITING","poll":attempt,"observed_check_count":len(checks),"pending_count":len(pending),"pending_checks":summarize(pending),"seconds_remaining":remaining}
        signature = json.dumps(payload, sort_keys=True)
        if signature != last_signature:
            print(json.dumps(payload, indent=2))
            last_signature = signature
        time.sleep(min(poll_interval(attempt, args.initial_poll_seconds, args.max_poll_seconds), remaining))


if __name__ == "__main__":
    raise SystemExit(main())