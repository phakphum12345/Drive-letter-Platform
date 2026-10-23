from __future__ import annotations

"""Owner-only local Flutter code editing service.

The service operates only inside an explicit allowlisted project root, uses a
content SHA to prevent TOCTOU overwrites, previews unified diffs before writes,
and validates every applied change with the external Flutter tool.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import time
import threading
from difflib import unified_diff
from pathlib import Path
from typing import Any

_APPLY_LOCK = threading.Lock()


def _atomic_write(path: Path, data: bytes) -> None:
    """Replace a file atomically using a temporary file in the same directory."""
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".research-os-tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp_path.replace(path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


MAX_FILE_BYTES = 1024 * 1024
MAX_LIST_ITEMS = 2000
BLOCKED_PARTS = {".git", ".dart_tool", "build", "__pycache__"}
BLOCKED_PREFIXES = (".github/workflows/",)
TEXT_EXTENSIONS = {
    ".dart", ".yaml", ".yml", ".json", ".md", ".txt", ".py", ".toml",
    ".xml", ".gradle", ".properties", ".html", ".css", ".js", ".ts",
}

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_newlines(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")

def _projects(root: Path) -> dict[str, Path]:
    configured = (os.environ.get("RESEARCH_OS_CODE_PROJECTS") or "").strip()
    result: dict[str, Path] = {}
    if configured:
        for item in configured.split(","):
            if "=" not in item:
                continue
            name, relative = item.split("=", 1)
            name, relative = name.strip(), relative.strip()
            if name and relative:
                result[name] = (root / relative).resolve()
    if not result:
        result["research_os_flutter"] = (root / "apps" / "research_os_flutter").resolve()
    return result

def _root() -> Path:
    configured = (os.environ.get("RESEARCH_OS_CODE_ROOT") or "").strip()
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]

def project_map() -> dict[str, str]:
    root = _root()
    return {name: str(path.relative_to(root)) for name, path in _projects(root).items() if path.is_dir()}

def _project(name: str) -> tuple[Path, Path]:
    root = _root()
    projects = _projects(root)
    if name not in projects:
        raise ValueError("unknown code project")
    project = projects[name]
    if not project.is_dir():
        raise ValueError("code project is not available")
    try:
        project.relative_to(root)
    except ValueError as exc:
        raise ValueError("code project escapes code root") from exc
    return root, project

def _safe_path(project: Path, relative: str) -> Path:
    value = relative.replace("\\", "/").strip()
    if not value or value.startswith("/") or ":" in value.split("/")[0]:
        raise ValueError("absolute paths are not allowed")
    candidate = (project / value).resolve()
    try:
        candidate.relative_to(project)
    except ValueError as exc:
        raise ValueError("path escapes project root") from exc
    rel = candidate.relative_to(project).as_posix()
    if any(part in BLOCKED_PARTS for part in candidate.relative_to(project).parts):
        raise ValueError("path is protected")
    if any(rel.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        raise ValueError("workflow files are protected")
    if candidate.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("unsupported source file type")
    return candidate

def list_files(project_name: str, query: str = "") -> dict[str, Any]:
    _, project = _project(project_name)
    query = query.strip().casefold()
    items: list[dict[str, Any]] = []
    for path in project.rglob("*"):
        if len(items) >= MAX_LIST_ITEMS:
            break
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(project)
            _safe_path(project, rel.as_posix())
        except (ValueError, OSError):
            continue
        if query and query not in rel.as_posix().casefold():
            continue
        items.append({"path": rel.as_posix(), "bytes": path.stat().st_size})
    items.sort(key=lambda item: item["path"])
    return {"project": project_name, "items": items, "count": len(items)}

def read_file(project_name: str, relative: str) -> dict[str, Any]:
    _, project = _project(project_name)
    path = _safe_path(project, relative)
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file is too large")
    content = _normalize_newlines(data.decode("utf-8"))
    return {
        "project": project_name,
        "path": path.relative_to(project).as_posix(),
        "content": content,
        "sha256": _sha_bytes(data),
        "bytes": len(data),
    }

def preview(project_name: str, relative: str, original_sha256: str, content: str) -> dict[str, Any]:
    current = read_file(project_name, relative)
    if current["sha256"] != original_sha256:
        raise RuntimeError("file changed since it was read; refresh before preview")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("file is too large")
    before = current["content"].splitlines(keepends=True)
    after = content.splitlines(keepends=True)
    diff = "".join(unified_diff(
        before, after,
        fromfile=f"a/{current['path']}",
        tofile=f"b/{current['path']}",
    ))
    return {
        "project": project_name,
        "path": current["path"],
        "original_sha256": original_sha256,
        "new_sha256": _sha(content),
        "changed": content != current["content"],
        "diff": diff,
    }

def _run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.time()
    completed = subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "duration_seconds": round(time.time() - started, 3),
    }

def validate(project_name: str) -> dict[str, Any]:
    _, project = _project(project_name)
    flutter = (os.environ.get("RESEARCH_OS_FLUTTER_COMMAND") or "flutter").strip()
    analyze = _run([flutter, "analyze"], project, 300)
    if analyze["exit_code"] != 0:
        return {"ok": False, "steps": [analyze]}
    test = _run([flutter, "test"], project, 600)
    return {"ok": test["exit_code"] == 0, "steps": [analyze, test]}

def apply(
    project_name: str,
    relative: str,
    original_sha256: str,
    content: str,
    principal: str,
) -> dict[str, Any]:
    # Serialize applies within this Python process.
    with _APPLY_LOCK:
        configured_owners = (
            os.environ.get("RESEARCH_OS_CODE_OWNER_IDS", ""),
            os.environ.get("RESEARCH_OS_OWNER_EMAILS", ""),
        )
        allowed = {
            item.strip().casefold()
            for setting in configured_owners
            for item in setting.split(",")
            if item.strip()
        }
        if not allowed or principal.strip().casefold() not in allowed:
            raise PermissionError("OWNER authority is required for code changes")

        _, project = _project(project_name)
        path = _safe_path(project, relative)
        current = read_file(project_name, relative)

        if current["sha256"] != original_sha256:
            raise RuntimeError("file changed since it was read; refresh before apply")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("file is too large")

        old_bytes = path.read_bytes()
        if _sha_bytes(old_bytes) != original_sha256:
            raise RuntimeError("file changed since it was read; refresh before apply")

        old_content = _normalize_newlines(old_bytes.decode("utf-8"))
        if old_content == content:
            return {
                "applied": False,
                "rolled_back": False,
                "validation": {"ok": True, "steps": []},
                "sha256": original_sha256,
            }

        new_bytes = content.encode("utf-8")
        written_sha256 = _sha_bytes(new_bytes)
        _atomic_write(path, new_bytes)

        try:
            validation = validate(project_name)
        except Exception as exc:
            validation = {
                "ok": False,
                "steps": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

        rolled_back = False
        rollback_conflict = False

        if not validation.get("ok", False):
            # Roll back only if the file still contains exactly our write.
            try:
                observed_sha256 = _sha_bytes(path.read_bytes())
            except OSError:
                observed_sha256 = None

            if observed_sha256 == written_sha256:
                try:
                    _atomic_write(path, old_bytes)
                    rolled_back = True
                except OSError:
                    rollback_conflict = True
            else:
                # Never overwrite a concurrent external change.
                rollback_conflict = True

        try:
            final_bytes = path.read_bytes()
            final_sha256 = _sha_bytes(final_bytes)
        except OSError:
            final_sha256 = None

        if not rolled_back and final_sha256 != written_sha256:
            rollback_conflict = True
        evidence = {
            "tool": "owner-flutter-code-tool",
            "principal": principal,
            "project": project_name,
            "path": current["path"],
            "before_sha256": original_sha256,
            "written_sha256": written_sha256,
            "observed_final_sha256": final_sha256,
            "validation": validation,
            "rolled_back": rolled_back,
            "rollback_conflict": rollback_conflict,
            "final_sha256": final_sha256,
            "timestamp": time.time(),
        }

        evidence_error = None
        evidence_path = None
        try:
            evidence_dir = _root() / "evidence" / "flutter-code-tool"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            evidence_path = evidence_dir / (
                f"{time.time_ns()}-{threading.get_ident()}.json"
            )
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError, TypeError) as exc:
            # File changes may already have completed; report evidence failure separately.
            evidence_error = f"{type(exc).__name__}: {exc}"
            evidence_path = None

        result = {
            "applied": bool(validation.get("ok", False) and final_sha256 == written_sha256),
            "rolled_back": rolled_back,
            "rollback_conflict": rollback_conflict,
            "evidence": str(evidence_path) if evidence_path else None,
            "evidence_error": evidence_error,
            "validation": validation,
            "sha256": final_sha256,
        }
        if "error" in validation:
            result["error"] = validation["error"]
        return result
