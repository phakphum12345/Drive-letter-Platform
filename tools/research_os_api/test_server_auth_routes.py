from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import multi_login_runtime
import oauth_handoff
import qr_pairing
import server_auth_routes


class ServerAuthRouteTests(unittest.TestCase):
    def test_callback_requires_code_and_state(self):
        with self.assertRaises(server_auth_routes.MultiLoginRuntimeError):
            server_auth_routes.auth_callback("github", "")

    def test_status_without_cookie_is_disconnected(self):
        result = server_auth_routes.auth_status(None)
        self.assertFalse(result["connected"])
        self.assertIsNone(result["account"])

    def test_non_google_qr_callback_waits_for_existing_session_approval(self):
        previous_data_dir = os.environ.get("RESEARCH_OS_DATA_DIR")
        previous_v3_data_dir = os.environ.get("RESEARCH_OS_V3_DATA_DIR")
        previous_session_secret = os.environ.get("RESEARCH_OS_SESSION_SECRET")
        with tempfile.TemporaryDirectory() as temp_dir:
            v3_data_dir = str(Path(temp_dir) / "v3-data")
            try:
                for provider in ("github", "microsoft"):
                    with self.subTest(provider=provider):
                        provider_env = {
                            "RESEARCH_OS_DATA_DIR": temp_dir,
                            "RESEARCH_OS_V3_DATA_DIR": v3_data_dir,
                            "RESEARCH_OS_SESSION_SECRET": "isolated-non-google-auth-test-secret",
                            f"RESEARCH_OS_{provider.upper()}_CLIENT_ID": f"{provider}-client-id",
                            f"RESEARCH_OS_{provider.upper()}_CLIENT_SECRET": f"{provider}-client-secret",
                        }
                        with patch.dict(os.environ, provider_env, clear=True):
                            pairing = qr_pairing.create_pairing()
                            redirect_uri = f"http://127.0.0.1:8787/v1/auth/{provider}/callback"
                            authorization_url = server_auth_routes.auth_pairing_authorize(
                                provider,
                                pairing["pairing_id"],
                                pairing["pairing_secret"],
                                redirect_uri,
                            )
                            state = parse_qs(urlparse(authorization_url).query)["state"][0]
                            self.assertNotIn("google", urlparse(authorization_url).netloc.lower())
                            self.assertNotIn("RESEARCH_OS_GOOGLE_CLIENT_ID", os.environ)
                            self.assertNotIn("RESEARCH_OS_GOOGLE_CLIENT_SECRET", os.environ)

                            if provider == "github":
                                profile_responses = [
                                    {
                                        "id": 123,
                                        "login": "test-github-user",
                                        "name": "Test GitHub User",
                                        "email": None,
                                    },
                                    [{"email": "github@example.com", "verified": True, "primary": True}],
                                ]
                            else:
                                profile_responses = [
                                    {
                                        "sub": "microsoft-sub-123",
                                        "email": "microsoft@example.com",
                                        "name": "Test Microsoft User",
                                    },
                                ]

                            def fake_token_exchange(url, data):
                                self.assertEqual(
                                    url,
                                    multi_login_runtime.get_provider(provider).token_endpoint,
                                )
                                self.assertEqual(
                                    data["client_id"],
                                    provider_env[f"RESEARCH_OS_{provider.upper()}_CLIENT_ID"],
                                )
                                self.assertEqual(
                                    data["client_secret"],
                                    provider_env[f"RESEARCH_OS_{provider.upper()}_CLIENT_SECRET"],
                                )
                                self.assertEqual(data["code"], "authorization-code")
                                self.assertEqual(data["redirect_uri"], redirect_uri)
                                return {"access_token": f"{provider}-access-token"}

                            with (
                                patch.object(
                                    multi_login_runtime,
                                    "_post_form",
                                    side_effect=fake_token_exchange,
                                ),
                                patch.object(
                                    multi_login_runtime,
                                    "_get_json",
                                    side_effect=profile_responses,
                                ),
                            ):
                                result, response_cookie = server_auth_routes.auth_callback(
                                    provider,
                                    f"code=authorization-code&state={state}",
                                )
                                self.assertIn("research_os_session", response_cookie)
                                self.assertEqual(result["provider"], provider)
                                expected_user_id = (
                                    "github:123"
                                    if provider == "github"
                                    else "microsoft:microsoft-sub-123"
                                )
                                self.assertEqual(result["principal"]["user_id"], expected_user_id)
                                self.assertEqual(
                                    result["pairing"]["pairing_secret"],
                                    pairing["pairing_secret"],
                                )

                                status = qr_pairing.get_status(
                                    pairing["pairing_id"],
                                    pairing["pairing_secret"],
                                )
                                self.assertEqual(status["status"], "SCANNED")
                                self.assertFalse(status["connected"])
                                self.assertFalse(status["handoff_ready"])

                                auth_status = server_auth_routes.auth_status(response_cookie)
                                self.assertTrue(auth_status["connected"])
                                self.assertEqual(auth_status["account"]["user_id"], expected_user_id)
                                self.assertEqual(
                                    auth_status["account"]["email"],
                                    result["principal"]["email"],
                                )

                                with self.assertRaisesRegex(
                                    server_auth_routes.MultiLoginRuntimeError,
                                    "missing, expired, or already consumed",
                                ):
                                    server_auth_routes.auth_provider_handoff(
                                        pairing["pairing_secret"]
                                    )

                                qr_pairing.claim_pairing_approval(
                                    pairing["pairing_id"],
                                    pairing["pairing_secret"],
                                )
                                oauth_handoff.create_handoff(
                                    Path(temp_dir) / "google_workspace",
                                    result["session"],
                                    "",
                                    code=pairing["pairing_secret"],
                                )
                                qr_pairing.complete_pairing(
                                    pairing["pairing_id"],
                                    provider=provider,
                                    account=result["principal"],
                                )
                                handoff = server_auth_routes.auth_provider_handoff(
                                    pairing["pairing_secret"]
                                )
                                self.assertTrue(handoff["connected"])
                                self.assertEqual(handoff["session"], result["session"])
                                self.assertEqual(
                                    handoff["account"]["user_id"],
                                    expected_user_id,
                                )
                                with self.assertRaisesRegex(
                                    server_auth_routes.MultiLoginRuntimeError,
                                    "missing, expired, or already consumed",
                                ):
                                    server_auth_routes.auth_provider_handoff(
                                        pairing["pairing_secret"]
                                    )
            finally:
                for key, previous in (
                    ("RESEARCH_OS_DATA_DIR", previous_data_dir),
                    ("RESEARCH_OS_V3_DATA_DIR", previous_v3_data_dir),
                    ("RESEARCH_OS_SESSION_SECRET", previous_session_secret),
                ):
                    if previous is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = previous



if __name__ == "__main__":
    unittest.main()
