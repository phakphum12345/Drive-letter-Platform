#!/usr/bin/env python3
"""Read-only GitHub dashboard adapter for Research OS.

The adapter keeps GitHub credentials on the API side. Public repositories work
without a token; private repositories require RESEARCH_OS_GITHUB_TOKEN or
GITHUB_TOKEN. Only compact dashboard fields are returned.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class GitHubStatusError(RuntimeError):
    pass


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "research-os-api",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    credential = token or os.getenv("RESEARCH_OS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    return headers


def _get_json(path: str, *, token: str | None = None) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers=_headers(token),
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubStatusError(f"GitHub HTTP {exc.code}: {body[:300]}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GitHubStatusError(f"GitHub request failed: {exc}") from exc



def _configured_accounts() -> list[dict[str, str]]:
    raw = os.getenv("RESEARCH_OS_GITHUB_ACCOUNTS_JSON", "").strip()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubStatusError("RESEARCH_OS_GITHUB_ACCOUNTS_JSON must be valid JSON") from exc
        if not isinstance(payload, list):
            raise GitHubStatusError("RESEARCH_OS_GITHUB_ACCOUNTS_JSON must be an array")
        result, seen = [], set()
        for item in payload:
            if not isinstance(item, dict):
                raise GitHubStatusError("each GitHub account entry must be an object")
            account_id, token = str(item.get("id") or "").strip(), str(item.get("token") or "").strip()
            label = str(item.get("label") or account_id).strip()
            if not account_id or not token or not label or account_id in seen:
                raise GitHubStatusError("GitHub account entries need unique IDs, labels, and tokens")
            seen.add(account_id)
            result.append({"id": account_id, "label": label, "token": token})
        return result
    token = os.getenv("RESEARCH_OS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    return [{"id": "default", "label": "Default GitHub token", "token": token}] if token else []


def _account_token(account_id: str | None) -> str | None:
    configured = _configured_accounts()
    if not configured:
        if account_id:
            raise ValueError("no GitHub account credentials are configured")
        return None
    if not account_id:
        if len(configured) == 1:
            return configured[0]["token"]
        raise ValueError("account_id is required when multiple GitHub accounts are configured")
    for account in configured:
        if account["id"] == account_id:
            return account["token"]
    raise ValueError("unknown GitHub account_id")


def accounts() -> dict[str, Any]:
    result = []
    for account in _configured_accounts():
        user = _get_json("/user", token=account["token"])
        result.append({"id": account["id"], "label": account["label"],
                       "login": str(user.get("login") or ""),
                       "name": str(user.get("name") or user.get("login") or account["label"]),
                       "credential_configured": True})
    return {"accounts": result, "read_only": True}


def repositories(account_id: str, *, page: int = 1, per_page: int = 100) -> dict[str, Any]:
    page, per_page = max(1, min(int(page), 100)), max(1, min(int(per_page), 100))
    token = _account_token(str(account_id or "").strip())
    if not token:
        raise ValueError("a configured GitHub account is required to list repositories")
    payload = _get_json(f"/user/repos?per_page={per_page}&page={page}&sort=updated&affiliation=owner,collaborator,organization_member", token=token)
    if not isinstance(payload, list):
        raise GitHubStatusError("GitHub repositories response has an invalid shape")
    items = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("full_name"):
            continue
        permissions = item.get("permissions") if isinstance(item.get("permissions"), dict) else {}
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        items.append({"full_name": str(item["full_name"]), "name": str(item.get("name") or ""),
                      "owner": str(owner.get("login") or ""), "default_branch": str(item.get("default_branch") or ""),
                      "private": bool(item.get("private")), "archived": bool(item.get("archived")),
                      "can_push": bool(permissions.get("push")), "admin": bool(permissions.get("admin")),
                      "url": str(item.get("html_url") or "")})
    return {"account_id": account_id, "repositories": items, "page": page,
            "per_page": per_page, "has_more": len(payload) == per_page, "read_only": True}


def _repo_path(repository: str, suffix: str = "") -> str:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise ValueError("repository must use owner/name format")
    encoded_owner = urllib.parse.quote(owner, safe="")
    encoded_name = urllib.parse.quote(name, safe="")
    return f"/repos/{encoded_owner}/{encoded_name}{suffix}"


def _artifact_items(artifacts: Any) -> list[dict[str, Any]]:
    items = artifacts.get("artifacts", []) if isinstance(artifacts, dict) else []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        workflow_run = item.get("workflow_run") or {}
        result.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "size_in_bytes": item.get("size_in_bytes"),
                "created_at": item.get("created_at"),
                "expires_at": item.get("expires_at"),
                "expired": bool(item.get("expired")),
                "archive_download_url": item.get("archive_download_url"),
                "digest": item.get("digest"),
                "workflow_run_id": workflow_run.get("id"),
                "workflow_run_name": workflow_run.get("name"),
                "workflow_run_head_branch": workflow_run.get("head_branch"),
                "workflow_run_conclusion": workflow_run.get("conclusion"),
                "workflow_run_url": workflow_run.get("html_url"),
            }
        )
    return result


def artifacts(repository: str, *, name: str | None = None, per_page: int = 30) -> dict[str, Any]:
    per_page = max(1, min(int(per_page), 100))
    suffix = f"/actions/artifacts?per_page={per_page}"
    if name and name.strip():
        suffix += "&name=" + urllib.parse.quote(name.strip(), safe="")
    payload = _get_json(_repo_path(repository, suffix))
    return {
        "repository": repository,
        "artifacts": _artifact_items(payload),
        "total_count": payload.get("total_count", 0) if isinstance(payload, dict) else 0,
        "credential_configured": bool(_configured_accounts()),
        "read_only": True,
    }


def dashboard(repository: str, *, account_id: str | None = None) -> dict[str, Any]:
    token = _account_token(account_id)
    repo = _get_json(_repo_path(repository), token=token)
    commits = _get_json(_repo_path(repository, "/commits?per_page=5"), token=token)
    pulls = _get_json(_repo_path(repository, "/pulls?state=open&per_page=5"), token=token)
    runs = _get_json(_repo_path(repository, "/actions/runs?per_page=5"), token=token)
    repo_artifacts = _get_json(_repo_path(repository, "/actions/artifacts?per_page=30"), token=token)

    if not isinstance(repo, dict):
        raise GitHubStatusError("GitHub repository response has an invalid shape")

    commit_items = []
    for item in commits if isinstance(commits, list) else []:
        commit = item.get("commit", {}) if isinstance(item, dict) else {}
        author = commit.get("author", {}) if isinstance(commit, dict) else {}
        commit_items.append(
            {
                "sha": str(item.get("sha", ""))[:7],
                "message": str(commit.get("message", "")).splitlines()[0],
                "author": str(author.get("name", "")),
                "date": author.get("date"),
                "url": item.get("html_url"),
            }
        )

    pull_items = []
    for item in pulls if isinstance(pulls, list) else []:
        pull_items.append(
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "author": (item.get("user") or {}).get("login"),
                "draft": bool(item.get("draft")),
                "url": item.get("html_url"),
            }
        )

    workflow_runs = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
    run_items = []
    for item in workflow_runs:
        run_items.append(
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "branch": item.get("head_branch"),
                "event": item.get("event"),
                "updated_at": item.get("updated_at"),
                "url": item.get("html_url"),
            }
        )

    return {
        "repository": repository,
        "account_id": account_id,
        "default_branch": repo.get("default_branch"),
        "visibility": repo.get("visibility", "private" if repo.get("private") else "public"),
        "open_issues_count": repo.get("open_issues_count", 0),
        "watchers_count": repo.get("subscribers_count", repo.get("watchers_count", 0)),
        "forks_count": repo.get("forks_count", 0),
        "updated_at": repo.get("updated_at"),
        "url": repo.get("html_url"),
        "commits": commit_items,
        "pull_requests": pull_items,
        "workflow_runs": run_items,
        "artifacts": _artifact_items(repo_artifacts),
        "credential_configured": bool(
            os.getenv("RESEARCH_OS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        ),
        "read_only": True,
    }
