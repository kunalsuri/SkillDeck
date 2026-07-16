import unittest
from unittest.mock import patch, MagicMock
import tempfile
from pathlib import Path

from kitchen import precheck


class TestPrecheckToken(unittest.TestCase):
    def test_token_from_env_var(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_real_token"}, clear=False):
            result, token = precheck.check_github_token()
        self.assertEqual(result.status, "ok")
        self.assertEqual(token, "ghp_real_token")

    def test_token_from_dotenv_file_when_env_var_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("GITHUB_TOKEN=ghp_from_dotenv\n", encoding="utf-8")
            with patch.object(precheck, "ENV_FILE", env_path), \
                 patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GITHUB_TOKEN", None)
                result, token = precheck.check_github_token()
        self.assertEqual(result.status, "ok")
        self.assertEqual(token, "ghp_from_dotenv")

    def test_placeholder_token_in_dotenv_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("GITHUB_TOKEN=ghp_your_token_here\n", encoding="utf-8")
            with patch.object(precheck, "ENV_FILE", env_path), \
                 patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GITHUB_TOKEN", None)
                result, token = precheck.check_github_token()
        self.assertEqual(result.status, "fail")
        self.assertIsNone(token)

    def test_no_token_anywhere_warns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"  # does not exist
            with patch.object(precheck, "ENV_FILE", env_path), \
                 patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GITHUB_TOKEN", None)
                result, token = precheck.check_github_token()
        self.assertEqual(result.status, "warn")
        self.assertIsNone(token)


class TestPrecheckNetwork(unittest.TestCase):
    @patch("kitchen.precheck.requests")
    def test_tls_ssl_error_reported_as_fail(self, mock_requests):
        import requests as real_requests
        mock_requests.exceptions.SSLError = real_requests.exceptions.SSLError
        mock_requests.exceptions.ConnectionError = real_requests.exceptions.ConnectionError
        mock_requests.exceptions.Timeout = real_requests.exceptions.Timeout
        mock_requests.get.side_effect = real_requests.exceptions.SSLError("cert verify failed")
        result = precheck.check_tls_and_reachability()
        self.assertEqual(result.status, "fail")
        self.assertIn("TLS handshake failed", result.message)

    @patch("kitchen.precheck.requests")
    def test_tls_success_reported_as_ok(self, mock_requests):
        mock_requests.get.return_value = MagicMock(status_code=200)
        result = precheck.check_tls_and_reachability()
        self.assertEqual(result.status, "ok")

    @patch("kitchen.precheck.requests")
    def test_github_api_auth_rejects_bad_token(self, mock_requests):
        mock_requests.get.return_value = MagicMock(status_code=401)
        result = precheck.check_github_api_auth("bad-token")
        self.assertEqual(result.status, "fail")
        self.assertIn("401", result.message)

    @patch("kitchen.precheck.requests")
    def test_github_api_auth_ok_with_remaining_quota(self, mock_requests):
        mock_requests.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"resources": {"core": {"limit": 5000, "remaining": 4999}}},
        )
        result = precheck.check_github_api_auth("good-token")
        self.assertEqual(result.status, "ok")
        self.assertIn("4999/5000", result.message)

    @patch("kitchen.precheck.requests")
    def test_github_api_auth_exhausted_quota_fails(self, mock_requests):
        mock_requests.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"resources": {"core": {"limit": 60, "remaining": 0}}},
        )
        result = precheck.check_github_api_auth(None)
        self.assertEqual(result.status, "fail")
        self.assertIn("exhausted", result.message)


class TestRunPrecheck(unittest.TestCase):
    @patch("kitchen.precheck.check_writable_dirs")
    @patch("kitchen.precheck.check_github_api_auth")
    @patch("kitchen.precheck.check_tls_and_reachability")
    @patch("kitchen.precheck.check_dns")
    @patch("kitchen.precheck.check_github_token")
    @patch("kitchen.precheck.check_python_deps")
    def test_all_ok_returns_true(
        self, mock_deps, mock_token, mock_dns, mock_tls, mock_auth, mock_dirs
    ):
        mock_deps.return_value = precheck.CheckResult("deps", "ok", "fine")
        mock_token.return_value = (precheck.CheckResult("token", "ok", "fine"), "tok")
        mock_dns.return_value = precheck.CheckResult("dns", "ok", "fine")
        mock_tls.return_value = precheck.CheckResult("tls", "ok", "fine")
        mock_auth.return_value = precheck.CheckResult("auth", "ok", "fine")
        mock_dirs.return_value = precheck.CheckResult("dirs", "ok", "fine")
        self.assertTrue(precheck.run_precheck())

    @patch("kitchen.precheck.check_writable_dirs")
    @patch("kitchen.precheck.check_tls_and_reachability")
    @patch("kitchen.precheck.check_dns")
    @patch("kitchen.precheck.check_github_token")
    @patch("kitchen.precheck.check_python_deps")
    def test_tls_failure_returns_false(
        self, mock_deps, mock_token, mock_dns, mock_tls, mock_dirs
    ):
        mock_deps.return_value = precheck.CheckResult("deps", "ok", "fine")
        mock_token.return_value = (precheck.CheckResult("token", "ok", "fine"), "tok")
        mock_dns.return_value = precheck.CheckResult("dns", "ok", "fine")
        mock_tls.return_value = precheck.CheckResult("tls", "fail", "broken")
        mock_dirs.return_value = precheck.CheckResult("dirs", "ok", "fine")
        self.assertFalse(precheck.run_precheck())

    @patch("kitchen.precheck.check_writable_dirs")
    @patch("kitchen.precheck.check_github_api_auth")
    @patch("kitchen.precheck.check_tls_and_reachability")
    @patch("kitchen.precheck.check_dns")
    @patch("kitchen.precheck.check_github_token")
    @patch("kitchen.precheck.check_python_deps")
    def test_warn_only_still_returns_true(
        self, mock_deps, mock_token, mock_dns, mock_tls, mock_auth, mock_dirs
    ):
        mock_deps.return_value = precheck.CheckResult("deps", "ok", "fine")
        mock_token.return_value = (precheck.CheckResult("token", "warn", "no token"), None)
        mock_dns.return_value = precheck.CheckResult("dns", "ok", "fine")
        mock_tls.return_value = precheck.CheckResult("tls", "ok", "fine")
        mock_auth.return_value = precheck.CheckResult("auth", "warn", "unauthenticated")
        mock_dirs.return_value = precheck.CheckResult("dirs", "ok", "fine")
        self.assertTrue(precheck.run_precheck())


if __name__ == "__main__":
    unittest.main()
