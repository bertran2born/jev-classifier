import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import fitz
import requests

import jev_pdf_audit as audit


def response_body():
    answers = {}
    for name, question in audit.QUESTIONS.items():
        labels = list(question["criteria"])
        probabilities = {label: 0.1 / (len(labels) - 1) for label in labels}
        probabilities[labels[0]] = 0.9
        answers[name] = {"type": "choice", "choice": labels[0],
                         "probabilities": probabilities, "confidence": 0.85}
    return {"model": "jev-test", "answers": answers, "usage": {"input_tokens": 123}}


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdfs = self.root / "pdfs"
        self.pdfs.mkdir()
        self.pdf = self.pdfs / "study.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            text = ("Methods: We preregistered the regression and exclusion criteria.\n"
                    "Results: The primary hypothesis was supported (p < 0.01).\n"
                    "Sensitivity analyses and Bonferroni correction were reported.\n") * 8
            page.insert_text((50, 50), text, fontsize=10)
            doc.save(self.pdf)
        self.out = self.root / "results"
        self.out.mkdir()

    def cli(self, *args):
        with patch.object(sys, "argv", ["audit", str(self.pdfs), "--out", str(self.out), *args]), \
                contextlib.redirect_stdout(io.StringIO()):
            return audit.main()

    def test_real_pdf_extraction_without_network(self):
        with patch.object(audit.requests, "post", side_effect=AssertionError("network")):
            self.assertEqual(self.cli("--dry-run"), 0)
        row = json.loads((self.out / "dry-run.jsonl").read_text())
        self.assertEqual(row["status"], "dry_run")
        self.assertEqual(row["pages_used"], "1")
        self.assertIn("[PDF page 1]", Path(row["excerpt_file"]).read_text())
        self.assertTrue((self.out / "dry-run.csv").exists())

    def test_packet_limit_includes_instructions(self):
        excerpts = [(10, 1, "Methods and results. " * 1000)]
        packet, pages = audit.build_packet(excerpts, 1000)
        self.assertEqual(len(packet), 1000)
        self.assertEqual(pages, [1])

    def test_api_contract_and_retry(self):
        busy = Mock(status_code=429, headers={"Retry-After": "1"})
        success = Mock(status_code=200)
        success.json.return_value = response_body()
        with patch.object(audit.requests, "post", side_effect=[busy, success]) as post, \
                patch.object(audit.time, "sleep") as sleep:
            result = audit.ask_jev("excerpts", "test-key")
        self.assertEqual(result["model"], "jev-test")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["questions"], audit.QUESTIONS)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        sleep.assert_called_once()

    def test_rejects_incomplete_or_invalid_answers(self):
        invalid = [[], {"answers": {}}, response_body(), response_body(), response_body()]
        invalid[2]["answers"]["field"]["choice"] = "invalid"
        invalid[3]["answers"]["field"]["probabilities"]["genetics"] = float("nan")
        invalid[4]["answers"]["field"]["confidence"] = 2
        for body in invalid:
            with self.subTest(body=body):
                response = Mock(status_code=200)
                response.json.return_value = body
                with patch.object(audit.requests, "post", return_value=response):
                    with self.assertRaises(ValueError):
                        audit.ask_jev("excerpts", "test-key")

    def test_http_auth_error_is_not_retried(self):
        response = Mock(status_code=401)
        response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        with patch.object(audit.requests, "post", return_value=response) as post:
            with self.assertRaises(requests.HTTPError):
                audit.ask_jev("excerpts", "test-key")
        self.assertEqual(post.call_count, 1)

    def test_resume_parameters_and_dry_run_preservation(self):
        with patch.dict(audit.os.environ, {"TYPESAFE_API_KEY": "test-key"}), \
                patch.object(audit, "ask_jev", return_value=response_body()) as ask:
            self.assertEqual(self.cli(), 0)
            journal = (self.out / "results.jsonl").read_bytes()
            csv = (self.out / "results.csv").read_bytes()
            self.assertEqual(self.cli(), 0)
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(self.cli("--dry-run"), 0)
            self.assertEqual((self.out / "results.jsonl").read_bytes(), journal)
            self.assertEqual((self.out / "results.csv").read_bytes(), csv)
            self.assertEqual(self.cli("--max-pages", "2"), 0)
            self.assertEqual(ask.call_count, 2)

    def test_failure_is_saved_and_exit_code_nonzero(self):
        with patch.dict(audit.os.environ, {"TYPESAFE_API_KEY": "test-key"}), \
                patch.object(audit, "ask_jev", side_effect=ValueError("invalid response")):
            self.assertEqual(self.cli(), 1)
        row = json.loads((self.out / "results.jsonl").read_text())
        self.assertEqual(row["status"], "error")
        self.assertTrue((self.out / "results.csv").exists())

    def test_scanned_and_corrupt_pdf(self):
        blank = self.pdfs / "blank.pdf"
        with fitz.open() as doc:
            doc.new_page()
            doc.save(blank)
        bad = self.pdfs / "broken.pdf"
        bad.write_bytes(b"not a PDF")
        for pdf, status in [(blank, "needs_ocr"), (bad, "error")]:
            row = audit.analyze_pdf(pdf, self.out, None, 100, 22000, True)
            self.assertEqual(row["status"], status)

    def test_negative_limit_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                self.cli("--limit", "-1", "--dry-run")
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
