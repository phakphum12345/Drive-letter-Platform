from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import qr_pairing


class QRPairingTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("RESEARCH_OS_DATA_DIR")
        os.environ["RESEARCH_OS_DATA_DIR"] = self.data.name

    def tearDown(self):
        if self.prev is None:
            os.environ.pop("RESEARCH_OS_DATA_DIR", None)
        else:
            os.environ["RESEARCH_OS_DATA_DIR"] = self.prev
        self.data.cleanup()

    def test_secret_is_hashed_at_rest(self):
        created = qr_pairing.create_pairing()
        raw = Path(self.data.name, "qr_pairings.json").read_text(encoding="utf-8")
        self.assertNotIn(created["pairing_secret"], raw)
        self.assertEqual(qr_pairing.get_status(created["pairing_id"], created["pairing_secret"])["status"], "PENDING")

    def test_invalid_secret_fails_closed(self):
        created = qr_pairing.create_pairing()
        with self.assertRaises(qr_pairing.QRPairingError):
            qr_pairing.get_status(created["pairing_id"], "wrong")

    def test_oauth_binding_is_single_use(self):
        created = qr_pairing.create_pairing()
        qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "oauth-state", "github")
        binding = qr_pairing.consume_oauth_binding("oauth-state")
        self.assertEqual(binding["pairing_id"], created["pairing_id"])
        self.assertEqual(binding["pairing_secret"], created["pairing_secret"])
        self.assertIsNone(qr_pairing.consume_oauth_binding("oauth-state"))

    def test_rebinding_scanned_pairing_is_rejected_without_overwriting_original_state(self):
        created = qr_pairing.create_pairing()
        qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "first-state", "github")
        with self.assertRaises(qr_pairing.QRPairingError):
            qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "second-state", "google")
        self.assertIsNotNone(qr_pairing.consume_oauth_binding("first-state"))
        self.assertIsNone(qr_pairing.consume_oauth_binding("second-state"))

    def test_concurrent_bind_is_atomic_and_only_one_state_wins(self):
        created = qr_pairing.create_pairing()
        barrier = threading.Barrier(3)
        outcomes = []
        guard = threading.Lock()

        def bind(state):
            barrier.wait()
            try:
                qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], state, "github")
                outcome = ("ok", state)
            except qr_pairing.QRPairingError:
                outcome = ("rejected", state)
            with guard:
                outcomes.append(outcome)

        workers = [threading.Thread(target=bind, args=(state,)) for state in ("state-a", "state-b")]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive(), "pairing transition deadlocked")

        self.assertEqual(sum(kind == "ok" for kind, _ in outcomes), 1)
        self.assertEqual(sum(kind == "rejected" for kind, _ in outcomes), 1)
        winner = next(value for kind, value in outcomes if kind == "ok")
        loser = next(value for kind, value in outcomes if kind == "rejected")
        self.assertIsNotNone(qr_pairing.consume_oauth_binding(winner))
        self.assertIsNone(qr_pairing.consume_oauth_binding(loser))

    def test_expired_pairing_is_denied_even_if_record_was_connected(self):
        created = qr_pairing.create_pairing()
        qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "oauth-state", "github")
        qr_pairing.claim_pairing_approval(created["pairing_id"], created["pairing_secret"])
        qr_pairing.complete_pairing(created["pairing_id"], provider="github", account={"user_id": "u1"})
        path = Path(self.data.name, "qr_pairings.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pairings"][created["pairing_id"]]["expires_at"] = 1
        path.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(qr_pairing.time, "time", return_value=100):
            with self.assertRaisesRegex(qr_pairing.QRPairingError, "expired"):
                qr_pairing.get_status(created["pairing_id"], created["pairing_secret"])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["pairings"][created["pairing_id"]]["status"], "EXPIRED")

    def test_authenticated_approval_claim_is_single_use(self):
        pairing = qr_pairing.create_pairing()
        scanned = qr_pairing.claim_pairing_approval(
            pairing["pairing_id"],
            pairing["pairing_secret"],
        )
        self.assertEqual(scanned["status"], "SCANNED")
        with self.assertRaisesRegex(qr_pairing.QRPairingError, "already claimed"):
            qr_pairing.claim_pairing_approval(
                pairing["pairing_id"],
                pairing["pairing_secret"],
            )
        qr_pairing.release_pairing_approval(
            pairing["pairing_id"],
            pairing["pairing_secret"],
        )
        claimed_again = qr_pairing.claim_pairing_approval(
            pairing["pairing_id"],
            pairing["pairing_secret"],
        )
        self.assertEqual(claimed_again["status"], "SCANNED")

    def test_connected_pairing_cannot_be_cancelled(self):
        created = qr_pairing.create_pairing()
        qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "oauth-state", "github")
        qr_pairing.claim_pairing_approval(created["pairing_id"], created["pairing_secret"])
        qr_pairing.complete_pairing(created["pairing_id"], provider="github", account={"user_id": "u1"})
        with self.assertRaisesRegex(qr_pairing.QRPairingError, "cannot be cancelled"):
            qr_pairing.cancel_pairing(created["pairing_id"], created["pairing_secret"])
        self.assertEqual(qr_pairing.get_status(created["pairing_id"], created["pairing_secret"])["status"], "CONNECTED")

    def test_completed_pairing_never_persists_session(self):
        created = qr_pairing.create_pairing()
        qr_pairing.bind_oauth_state(created["pairing_id"], created["pairing_secret"], "oauth-state", "github")
        qr_pairing.claim_pairing_approval(created["pairing_id"], created["pairing_secret"])
        qr_pairing.complete_pairing(
            created["pairing_id"],
            provider="github",
            account={"user_id": "github:123", "email": "owner@example.com", "role": "OWNER", "session": "SECRET"},
        )
        raw = Path(self.data.name, "qr_pairings.json").read_text(encoding="utf-8")
        self.assertNotIn("SECRET", raw)
        self.assertTrue(qr_pairing.get_status(created["pairing_id"], created["pairing_secret"])["connected"])


if __name__ == "__main__":
    unittest.main()
