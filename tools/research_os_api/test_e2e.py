import json
import os
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server
import server_auth_routes
import auth_session
import qr_pairing
from server import ResearchOSHandler
from unittest.mock import patch


class ResearchOSEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_ai_route = os.environ.get("RESEARCH_OS_AI_ROUTE")
        os.environ["RESEARCH_OS_AI_ROUTE"] = "friend"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ResearchOSHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        if cls.previous_ai_route is None:
            os.environ.pop("RESEARCH_OS_AI_ROUTE", None)
        else:
            os.environ["RESEARCH_OS_AI_ROUTE"] = cls.previous_ai_route

    def request_json(self, path, payload=None, headers=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_non_google_pairing_callback_sets_cookie_and_redirects_to_approval(self):
        cookie = "research_os_session=signed-session; Path=/; HttpOnly; Secure; SameSite=Lax"
        payload = {
            "provider": "github",
            "principal": {"email": "user@example.com"},
            "pairing": {
                "pairing_id": "pair-123",
                "pairing_secret": "pairing-secret",
                "paired": False,
                "provider": "github",
            },
        }
        with patch.object(
            server_auth_routes,
            "auth_callback",
            return_value=(payload, cookie),
        ):
            request = urllib.request.Request(
                self.base_url + "/v1/auth/github/callback?code=test-code&state=test-state",
                method="GET",
            )

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(NoRedirect)
            try:
                response = opener.open(request, timeout=5)
            except urllib.error.HTTPError as exc:
                response = exc
            self.assertEqual(response.code, 303)
            self.assertIn(cookie, response.headers.get_all("Set-Cookie") or [])
            self.assertIn("/v1/auth/pairing/open?", response.headers["Location"])
            self.assertIn("pairing-secret", response.headers["Location"])

    def test_google_pairing_callback_redirects_to_approval_with_cookie(self):
        cookie = "research_os_session=google-signed-session; Path=/; HttpOnly; Secure; SameSite=Lax"
        payload = {
            "provider": "google",
            "account": {"email": "google-user@example.com"},
            "pairing": {
                "pairing_id": "google-pair-123",
                "pairing_secret": "google-pairing-secret",
                "paired": False,
                "provider": "google",
            },
        }
        with patch.object(
            server_auth_routes,
            "google_auth_callback",
            return_value=(payload, cookie),
        ):
            request = urllib.request.Request(
                self.base_url + "/v1/auth/google/callback?code=test-code&state=test-state",
                method="GET",
            )

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(NoRedirect)
            try:
                response = opener.open(request, timeout=5)
            except urllib.error.HTTPError as exc:
                response = exc
            self.assertEqual(response.code, 303)
            self.assertIn(cookie, response.headers.get_all("Set-Cookie") or [])
            self.assertIn("/v1/auth/pairing/open?", response.headers["Location"])
            self.assertIn("google-pairing-secret", response.headers["Location"])

    def test_pairing_approval_reuses_existing_session_and_handoff_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_OS_DATA_DIR": temp_dir,
                    "RESEARCH_OS_V3_DATA_DIR": str(Path(temp_dir) / "v3-data"),
                    "RESEARCH_OS_SESSION_SECRET": "isolated-pairing-approval-test-secret",
                },
                clear=True,
            ):
                session = auth_session.issue_session({
                    "user_id": "github:device-user",
                    "email": "device-user@example.com",
                    "role": "user",
                })
                pairing = qr_pairing.create_pairing()
                cookie_header = f"research_os_session={session}"
                approval_url = (
                    "/v1/auth/pairing/open?pairing_id="
                    + pairing["pairing_id"]
                    + "&secret="
                    + pairing["pairing_secret"]
                )
                request = urllib.request.Request(
                    self.base_url + approval_url,
                    headers={"Cookie": cookie_header},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html = response.read().decode("utf-8")
                    self.assertIn("Approve this device", html)
                    self.assertIn("Approve device", html)

                with self.assertRaises(urllib.error.HTTPError) as unauthenticated:
                    self.request_json(
                        "/v1/auth/pairing/approve",
                        {
                            "pairing_id": pairing["pairing_id"],
                            "pairing_secret": pairing["pairing_secret"],
                        },
                    )
                self.assertEqual(unauthenticated.exception.code, 401)

                status, approved = self.request_json(
                    "/v1/auth/pairing/approve",
                    {
                        "pairing_id": pairing["pairing_id"],
                        "pairing_secret": pairing["pairing_secret"],
                    },
                    headers={"Cookie": cookie_header},
                )
                self.assertEqual(status, 200)
                self.assertTrue(approved["connected"])
                self.assertEqual(approved["status"], "CONNECTED")

                status, pairing_status = self.request_json(
                    "/v1/auth/pairing/status?pairing_id="
                    + pairing["pairing_id"]
                    + "&secret="
                    + pairing["pairing_secret"]
                )
                self.assertEqual(status, 200)
                self.assertTrue(pairing_status["connected"])
                self.assertEqual(
                    pairing_status["account"]["email"],
                    "device-user@example.com",
                )

                status, handoff = self.request_json(
                    "/v1/auth/providers/handoff",
                    {},
                    headers={"X-Research-OS-OAuth-State": pairing["pairing_secret"]},
                )
                self.assertEqual(status, 200)
                self.assertEqual(handoff["session"], session)
                self.assertTrue(handoff["connected"])

                with self.assertRaises(urllib.error.HTTPError) as replay:
                    self.request_json(
                        "/v1/auth/providers/handoff",
                        {},
                        headers={"X-Research-OS-OAuth-State": pairing["pairing_secret"]},
                    )
                self.assertIn(replay.exception.code, {400, 401})

    def test_pairing_base_url_requires_https_for_public_hosts(self):
        handler = object.__new__(ResearchOSHandler)
        handler.headers = {"Host": "research-os.example"}

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "HTTPS URL"):
                handler._pairing_base_url()

        with patch.dict(
            os.environ,
            {"RESEARCH_OS_PUBLIC_BASE_URL": "https://research-os.example"},
            clear=True,
        ):
            self.assertEqual(
                handler._pairing_base_url(),
                "https://research-os.example",
            )

        with patch.dict(
            os.environ,
            {"RESEARCH_OS_PAIRING_BASE_URL": "http://research-os.example"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                handler._pairing_base_url()

    def test_pairing_base_url_allows_http_only_for_loopback(self):
        handler = object.__new__(ResearchOSHandler)
        handler.headers = {"Host": "127.0.0.1:8787"}

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(handler._pairing_base_url(), "http://127.0.0.1:8787")

    def test_living_house_flow(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("ยินดีต้อนรับกลับครับเพื่อน", html)
        self.assertIn("เริ่มงาน", html)

        status, health = self.request_json("/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ui"])

        session_id = "e2e-session"
        with patch.object(
            server,
            "_friend_chat",
            return_value={"provider": "mock", "text": "ช่วยสรุปภารกิจของบ้าน"},
        ):
            status, generated = self.request_json(
                "/v1/ai/generate",
                {
                    "provider": "mock",
                    "prompt": "ช่วยสรุปภารกิจของบ้าน",
                    "session_id": session_id,
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(generated["provider"], "mock")
        self.assertEqual(generated["session_id"], session_id)
        self.assertTrue(generated["text"])

        status, captured = self.request_json(
            "/v1/conversations/analyze",
            {
                "conversation": [
                    {"role": "user", "content": "เราควรสร้าง Entrance UI และเชื่อม API"},
                    {"role": "assistant", "content": generated["text"]},
                ],
                "title": "E2E Session",
                "tags": ["e2e"],
                "min_quality": 20,
            },
        )
        self.assertEqual(status, 200)
        self.assertIn("artifact", captured)
        self.assertFalse(captured["persisted"])


if __name__ == "__main__":
    unittest.main()
