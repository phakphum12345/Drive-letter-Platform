from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from threading import Lock
from typing import Any

PAIRING_TTL_SECONDS = 180
STATE_SCHEMA = "RESEARCH_OS_QR_PAIRING_V1"
_FILENAME = "qr_pairings.json"
_LOCK = Lock()


class QRPairingError(ValueError):
    # Invalid, expired, cancelled, or already-consumed pairing.
    pass


def _root() -> Path:
    configured = (os.getenv("RESEARCH_OS_DATA_DIR") or "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        try:
            from google_identity import GoogleIdentityBroker
        except ImportError:
            from .google_identity import GoogleIdentityBroker
        root = GoogleIdentityBroker().root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / _FILENAME


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _read() -> dict[str, Any]:
    path = _path()
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
        return {"schema": STATE_SCHEMA, "pairings": {}}
    pairings = value.get("pairings")
    return {"schema": STATE_SCHEMA, "pairings": pairings if isinstance(pairings, dict) else {}}


def _write(value: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _prune(pairings: dict[str, Any], now: int) -> bool:
    changed = False
    for record in pairings.values():
        if not isinstance(record, dict):
            continue
        if int(record.get("expires_at", 0)) <= now and record.get("status") not in {"CANCELLED", "EXPIRED"}:
            record["status"] = "EXPIRED"
            record.pop("oauth_state", None)
            record.pop("_pending_secret", None)
            changed = True
    return changed


def create_pairing() -> dict[str, Any]:
    now = int(time.time())
    pairing_id = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    record = {
        "pairing_id": pairing_id,
        "secret_hash": _digest(secret),
        "created_at": now,
        "expires_at": now + PAIRING_TTL_SECONDS,
        "status": "PENDING",
    }
    with _LOCK:
        state = _read()
        _prune(state["pairings"], now)
        state["pairings"][pairing_id] = record
        _write(state)
    return {"pairing_id": pairing_id, "pairing_secret": secret, "expires_at": record["expires_at"], "status": record["status"]}


def _validated_locked(state: dict[str, Any], pairing_id: str, secret: str, now: int) -> dict[str, Any]:
    """Validate a pairing while the caller holds _LOCK; return its live record."""
    pid = str(pairing_id or "").strip()
    supplied = str(secret or "").strip()
    if not pid or not supplied:
        raise QRPairingError("pairing_id and pairing_secret are required")
    record = state["pairings"].get(pid)
    if not isinstance(record, dict):
        raise QRPairingError("pairing is missing or expired")
    expected = str(record.get("secret_hash") or "")
    if not expected or not hmac.compare_digest(expected, _digest(supplied)):
        raise QRPairingError("pairing secret is invalid")
    if int(record.get("expires_at", 0)) <= now:
        record["status"] = "EXPIRED"
        record.pop("oauth_state", None)
        record.pop("_pending_secret", None)
        raise QRPairingError("pairing is expired")
    if record.get("status") == "CANCELLED":
        raise QRPairingError("pairing is cancelled")
    if record.get("status") == "EXPIRED":
        raise QRPairingError("pairing is expired")
    return record


def get_status(pairing_id: str, secret: str) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        now = int(time.time())
        changed = _prune(state["pairings"], now)
        try:
            record = _validated_locked(state, pairing_id, secret, now)
        except QRPairingError:
            if changed:
                _write(state)
            else:
                # Persist EXPIRED status set by validation when applicable.
                record = state["pairings"].get(str(pairing_id or "").strip())
                if isinstance(record, dict) and record.get("status") == "EXPIRED":
                    _write(state)
            raise
        if changed:
            _write(state)
        account = record.get("account") if isinstance(record.get("account"), dict) else None
        return {
            "pairing_id": record["pairing_id"],
            "status": record["status"],
            "expires_at": record["expires_at"],
            "connected": record["status"] == "CONNECTED",
            "handoff_ready": record["status"] == "CONNECTED",
            "account": account,
        }


def bind_oauth_state(pairing_id: str, secret: str, oauth_state: str, provider: str) -> None:
    value = str(oauth_state or "").strip()
    if not value:
        raise QRPairingError("oauth state is required")
    with _LOCK:
        state = _read()
        now = int(time.time())
        _prune(state["pairings"], now)
        record = _validated_locked(state, pairing_id, secret, now)
        if record.get("status") != "PENDING":
            _write(state)
            raise QRPairingError("pairing is not available")
        record["status"] = "SCANNED"
        record["oauth_state"] = value
        record["provider"] = str(provider or "").strip().lower()
        record["_pending_secret"] = str(secret).strip()
        _write(state)


def consume_oauth_binding(oauth_state: str) -> dict[str, str] | None:
    wanted = str(oauth_state or "").strip()
    if not wanted:
        return None
    with _LOCK:
        state = _read()
        _prune(state["pairings"], int(time.time()))
        for record in state["pairings"].values():
            if not isinstance(record, dict):
                continue
            candidate = str(record.get("oauth_state") or "")
            if candidate and hmac.compare_digest(candidate, wanted):
                if record.get("status") != "SCANNED" or int(record.get("expires_at", 0)) <= int(time.time()):
                    record["status"] = "EXPIRED"
                    record.pop("oauth_state", None)
                    record.pop("_pending_secret", None)
                    _write(state)
                    raise QRPairingError("pairing binding is expired or unavailable")
                secret = str(record.pop("_pending_secret", "") or "")
                pairing_id = str(record.get("pairing_id") or "")
                provider = str(record.get("provider") or "")
                record.pop("oauth_state", None)
                if not secret or not pairing_id:
                    _write(state)
                    raise QRPairingError("pairing binding is incomplete")
                _write(state)
                return {"pairing_id": pairing_id, "pairing_secret": secret, "provider": provider}
        _write(state)
    return None


def claim_pairing_approval(pairing_id: str, secret: str) -> dict[str, Any]:
    """Atomically claim approval so two authenticated scanners cannot race."""
    with _LOCK:
        state = _read()
        now = int(time.time())
        _prune(state["pairings"], now)
        record = _validated_locked(state, pairing_id, secret, now)
        if record.get("status") == "PENDING":
            record["status"] = "SCANNED"
            record["scanned_at"] = now
        if record.get("status") != "SCANNED" or record.get("approval_claimed"):
            _write(state)
            raise QRPairingError("pairing approval is already claimed or unavailable")
        record["approval_claimed"] = True
        _write(state)
        return {
            "pairing_id": record["pairing_id"],
            "status": record["status"],
            "expires_at": record["expires_at"],
        }


def release_pairing_approval(pairing_id: str, secret: str) -> None:
    """Release a claim only while the pairing remains uncompleted."""
    with _LOCK:
        state = _read()
        now = int(time.time())
        _prune(state["pairings"], now)
        record = _validated_locked(state, pairing_id, secret, now)
        if record.get("status") == "SCANNED":
            record.pop("approval_claimed", None)
            _write(state)



def complete_pairing(pairing_id: str, *, provider: str, account: dict[str, Any] | None) -> None:
    pid = str(pairing_id or "").strip()
    with _LOCK:
        state = _read()
        now = int(time.time())
        _prune(state["pairings"], now)
        record = state["pairings"].get(pid)
        if not isinstance(record, dict):
            _write(state)
            raise QRPairingError("pairing is missing")
        if int(record.get("expires_at", 0)) <= now or record.get("status") == "EXPIRED":
            record["status"] = "EXPIRED"
            record.pop("oauth_state", None)
            record.pop("_pending_secret", None)
            _write(state)
            raise QRPairingError("pairing expired before completion")
        if record.get("status") != "SCANNED" or not record.get("approval_claimed"):
            _write(state)
            raise QRPairingError("pairing approval has not been claimed")
        record["status"] = "CONNECTED"
        record["connected_at"] = now
        record["provider"] = str(provider or "").strip().lower()
        if isinstance(account, dict):
            record["account"] = {
                "user_id": str(account.get("user_id") or account.get("sub") or "").strip(),
                "email": str(account.get("email") or "").strip(),
                "role": str(account.get("role") or "").strip().lower(),
            }
        record.pop("oauth_state", None)
        record.pop("_pending_secret", None)
        record.pop("approval_claimed", None)
        _write(state)


def cancel_pairing(pairing_id: str, secret: str) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        now = int(time.time())
        _prune(state["pairings"], now)
        record = _validated_locked(state, pairing_id, secret, now)
        if record.get("status") not in {"PENDING", "SCANNED"} or record.get("approval_claimed"):
            _write(state)
            raise QRPairingError("pairing cannot be cancelled in its current state")
        record["status"] = "CANCELLED"
        record.pop("oauth_state", None)
        record.pop("_pending_secret", None)
        _write(state)
        return {"pairing_id": record["pairing_id"], "status": record["status"], "cancelled": True}
