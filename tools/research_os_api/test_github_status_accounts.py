from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from tools.research_os_api import github_status

class GitHubAccountSelectionTests(unittest.TestCase):
    def test_account_catalog_never_returns_token(self):
        configured='[{"id":"primary","label":"Primary","token":"secret-token"}]'
        with patch.dict(os.environ, {"RESEARCH_OS_GITHUB_ACCOUNTS_JSON": configured}, clear=True), patch.object(github_status, "_get_json", return_value={"login":"primary-user","name":"Primary User"}) as get_json:
            result=github_status.accounts()
        self.assertEqual(result["accounts"][0]["login"], "primary-user")
        self.assertNotIn("secret-token", str(result))
        get_json.assert_called_once_with("/user", token="secret-token")

    def test_multiple_accounts_require_explicit_selection(self):
        configured='[{"id":"one","token":"token-one"},{"id":"two","token":"token-two"}]'
        with patch.dict(os.environ, {"RESEARCH_OS_GITHUB_ACCOUNTS_JSON": configured}, clear=True):
            with self.assertRaisesRegex(ValueError, "account_id is required"):
                github_status._account_token(None)
            self.assertEqual(github_status._account_token("two"), "token-two")
            with self.assertRaisesRegex(ValueError, "unknown GitHub account_id"):
                github_status._account_token("missing")

    def test_repository_listing_uses_selected_token(self):
        configured='[{"id":"work","label":"Work","token":"private-token"}]'
        payload=[{"full_name":"example/project","name":"project","owner":{"login":"example"},"default_branch":"main","private":True,"permissions":{"push":True,"admin":False},"html_url":"https://github.com/example/project"}]
        with patch.dict(os.environ, {"RESEARCH_OS_GITHUB_ACCOUNTS_JSON": configured}, clear=True), patch.object(github_status, "_get_json", return_value=payload) as get_json:
            result=github_status.repositories("work")
        self.assertEqual(result["repositories"][0]["full_name"], "example/project")
        self.assertTrue(result["repositories"][0]["can_push"])
        self.assertNotIn("private-token", str(result))
        self.assertEqual(get_json.call_args.kwargs["token"], "private-token")

if __name__ == "__main__":
    unittest.main()
