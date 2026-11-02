import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import jev


class LauncherTests(unittest.TestCase):
    def test_default_command_opens_viewer(self):
        with patch.object(jev, "serve", return_value=0) as serve:
            self.assertEqual(jev.main([]), 0)
        serve.assert_called_once_with(8000, True)

    def test_port_and_no_browser(self):
        with patch.object(jev, "serve", return_value=0) as serve:
            self.assertEqual(jev.main(["--port", "8001", "--no-browser"]), 0)
        serve.assert_called_once_with(8001, False)

    def test_dry_run_needs_no_key_and_preserves_options(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(jev.getpass, "getpass") as prompt, \
                patch.object(jev.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(jev.main(["audit", "--dry-run", "--limit", "3"]), 0)
        prompt.assert_not_called()
        args, kwargs = run.call_args
        self.assertEqual(args[0][2:], ["pdfs", "--dry-run", "--limit", "3"])
        self.assertEqual(kwargs["cwd"], jev.ROOT)

    def test_key_is_passed_in_environment_only(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(jev.getpass, "getpass", return_value="temporary-test-key"), \
                patch.object(jev.subprocess, "run", return_value=Mock(returncode=1)) as run:
            self.assertEqual(jev.main(["audit", "--force"]), 1)
        args, kwargs = run.call_args
        self.assertNotIn("temporary-test-key", " ".join(args[0]))
        self.assertEqual(kwargs["env"]["TYPESAFE_API_KEY"], "temporary-test-key")
        self.assertNotIn("TYPESAFE_API_KEY", os.environ)

    def test_existing_key_and_custom_pdf_path(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), \
                patch.object(jev.getpass, "getpass") as prompt, \
                patch.object(jev.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(jev.main(["audit", "C:\\Mes études\\pdfs", "--limit", "50"]), 0)
        prompt.assert_not_called()
        self.assertEqual(run.call_args.args[0][2:], ["C:\\Mes études\\pdfs", "--limit", "50"])

    def test_help_needs_no_key(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(jev.getpass, "getpass") as prompt, \
                patch.object(jev.subprocess, "run", return_value=Mock(returncode=0)):
            self.assertEqual(jev.main(["audit", "--help"]), 0)
        prompt.assert_not_called()

    def test_cancelled_or_empty_key_never_calls_api(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(jev.subprocess, "run") as run, \
                contextlib.redirect_stderr(io.StringIO()):
            with patch.object(jev.getpass, "getpass", side_effect=EOFError):
                self.assertEqual(jev.main(["audit"]), 130)
            with patch.object(jev.getpass, "getpass", return_value=""):
                self.assertEqual(jev.main(["audit"]), 2)
        run.assert_not_called()

    def test_server_allows_only_viewer_and_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = ["index.html", "viewer.css", "viewer.js", "results.csv",
                     "pdfs/study.pdf", "jev-audit-results/results.csv",
                     "jev-audit-results/excerpts/study.txt", ".env", "jev.py",
                     "jev-audit-results/secret.txt", "pdfs/token.txt", "uv.lock"]
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            for path in paths[:7]:
                self.assertTrue(jev.public_path("/" + path, root), path)
            self.assertTrue(jev.public_path("/?refresh=1", root))
            for path in paths[7:] + ["pdfs/", "../.env", "%2eenv", "pdfs/../.env", "pdfs\\..\\.env", "C:/secret.pdf"]:
                self.assertFalse(jev.public_path("/" + path, root), path)

    def test_server_reports_occupied_port(self):
        with patch.object(jev, "ThreadingHTTPServer", side_effect=OSError("Port occupé")), \
                patch.object(jev.webbrowser, "open") as browser, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(jev.serve(), 1)
        browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
