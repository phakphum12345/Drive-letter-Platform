import os
import tempfile
import unittest
from unittest.mock import patch

from google_identity import GoogleIdentityBroker


class GoogleIdentityBrokerTest(unittest.TestCase):
    def test_identity_sign_in_uses_only_identity_scopes(self):
        env = {
            "RESEARCH_OS_GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "RESEARCH_OS_GOOGLE_CLIENT_SECRET": "client-secret",
            "RESEARCH_OS_API_PORT": "8787",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            broker = GoogleIdentityBroker(tmp)
            payload = broker.begin()
            url = payload["authorization_url"]
            self.assertIn("openid", url)
            self.assertIn("email", url)
            self.assertIn("profile", url)
            self.assertNotIn("gmail.modify", url)
            self.assertNotIn("spreadsheets", url)
            self.assertNotIn("calendar", url)
            self.assertIn("127.0.0.1%3A8787%2Fv1%2Fauth%2Fgoogle%2Fcallback", url)

    def test_identity_session_cookie_security_matches_redirect_scheme(self):
        from google_oauth import GoogleOAuthBroker
        import google_identity

        with tempfile.TemporaryDirectory() as tmp:
            for redirect_uri, expected_secure in (
                ("http://127.0.0.1:8787/v1/auth/google/callback", False),
                ("https://auth.example.com/v1/auth/google/callback", True),
            ):
                with self.subTest(redirect_uri=redirect_uri):
                    with (
                        patch.object(
                            GoogleOAuthBroker,
                            "complete",
                            return_value={
                                "account": {"email": "owner@example.com"},
                                "redirect_uri": redirect_uri,
                            },
                        ),
                        patch.object(google_identity, "issue_session", return_value="signed-session"),
                        patch.object(google_identity, "_current_http_handler", return_value=object()),
                        patch.object(google_identity, "_install_signout_cookie_hook"),
                        patch.object(
                            google_identity,
                            "cookie_header",
                            return_value="research_os_session=signed-session",
                        ) as cookie_header,
                    ):
                        GoogleIdentityBroker(tmp).complete(code="code", state="state")
                        self.assertEqual(
                            cookie_header.call_args.kwargs["secure"],
                            expected_secure,
                        )

    def test_render_external_url_becomes_mobile_callback(self):
        env = {
            "RESEARCH_OS_GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "RESEARCH_OS_GOOGLE_CLIENT_SECRET": "client-secret",
            "RENDER_EXTERNAL_URL": "https://research-os-api.example.com/",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            broker = GoogleIdentityBroker(tmp)
            self.assertEqual(
                broker.redirect_uri(),
                "https://research-os-api.example.com/v1/auth/google/callback",
            )

    def test_explicit_identity_redirect_wins(self):
        env = {
            "RESEARCH_OS_GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "RESEARCH_OS_GOOGLE_CLIENT_SECRET": "client-secret",
            "RENDER_EXTERNAL_URL": "https://research-os-api.example.com",
            "RESEARCH_OS_GOOGLE_IDENTITY_REDIRECT_URI": "https://auth.example.net/google/callback",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            broker = GoogleIdentityBroker(tmp)
            self.assertEqual(
                broker.redirect_uri(),
                "https://auth.example.net/google/callback",
            )


if __name__ == "__main__":
    unittest.main()
