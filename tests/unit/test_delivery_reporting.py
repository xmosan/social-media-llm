"""Provider acceptance is checked without leaking messages or credentials."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from app.config import settings
from app.logging_setup import AxiomHandler


class LogDeliveryChecks(unittest.TestCase):
    def setUp(self):
        for name, value in (("axiom_token", "private-token"), ("axiom_dataset", "fixture")):
            p = patch.object(settings, name, value); p.start(); self.addCleanup(p.stop)
        with patch("app.logging_setup.threading.Thread.start"):
            self.handler = AxiomHandler()
        self.addCleanup(self.handler.close)
        self.batch = [{"message": "private-message"}]

    def test_full_acceptance_is_required_and_failures_are_safe(self):
        for status, body in ((401, {}), (429, {}), (500, {}), (200, {"failed": 1, "ingested": 0}),
                             (200, {"failed": 0, "ingested": 0}), (200, {}), (200, [])):
            with self.subTest(status=status, body=body), patch("app.logging_setup.requests.post", return_value=Mock(status_code=status, json=lambda: body)), patch("sys.stderr", new_callable=io.StringIO) as output:
                self.handler._last_delivery_notice = None
                self.assertFalse(self.handler._send_to_axiom(self.batch))
                notice = json.loads(output.getvalue())
                self.assertEqual(notice["event"], "log_delivery_failed")
                self.assertNotIn("private", output.getvalue())

    def test_transport_and_invalid_json_never_expose_exception(self):
        for response in (Mock(side_effect=RuntimeError("private-token")), Mock(return_value=Mock(status_code=200, json=Mock(side_effect=ValueError("private-message"))))):
            with patch("app.logging_setup.requests.post", response), patch("sys.stderr", new_callable=io.StringIO) as output:
                self.handler._last_delivery_notice = None
                self.assertFalse(self.handler._send_to_axiom(self.batch))
                self.assertNotIn("private", output.getvalue())

    def test_failure_notices_are_throttled_and_recovery_does_not_claim_lost_batch_delivered(self):
        with patch("sys.stderr", new_callable=io.StringIO) as output:
            self.handler._delivery_notice(False, 2, "http_rejected", 401)
            self.handler._delivery_notice(False, 3, "http_rejected", 401)
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            with patch("app.logging_setup.requests.post", return_value=Mock(status_code=200, json=lambda: {"failed": 0, "ingested": 1})):
                self.assertTrue(self.handler._send_to_axiom(self.batch))
            notices = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(notices[-1]["event"], "log_delivery_recovered")
            self.assertEqual(notices[-1]["unconfirmed_events"], 5)
            self.assertEqual(notices[-1]["failed_batches"], 2)

    def test_full_queue_is_reported_without_dumping_record(self):
        import logging
        self.handler.setFormatter(logging.Formatter('{"message": "%(message)s"}'))
        with patch.object(self.handler.queue, "put_nowait", side_effect=RuntimeError("private-message")), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.handler.emit(logging.makeLogRecord({"msg": "private-message"}))
            self.assertEqual(json.loads(output.getvalue())["reason"], "queue_or_format_failed")
            self.assertNotIn("private", output.getvalue())


class EmailDeliveryChecks(unittest.TestCase):
    def setUp(self):
        # The main security harness stubs email; load the actual implementation
        # under a separate name and mock only its external transport.
        path = Path(__file__).resolve().parents[2] / "app/services/email.py"
        spec = importlib.util.spec_from_file_location("isolated_delivery_email", path)
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)

    def send(self):
        return asyncio.run(self.module.send_email("private@example.test", "Private subject", "Private body"))

    def test_missing_config_is_failure_without_console_email(self):
        with patch.object(settings, "resend_api_key", None), patch.object(self.module.resend.Emails, "send") as send, patch("sys.stdout", new_callable=io.StringIO) as output, self.assertLogs(self.module.logger, level="WARNING") as logs:
            self.assertFalse(self.send()); send.assert_not_called()
        self.assertNotIn("Private", output.getvalue() + str(logs.output))
        self.assertNotIn("private@example", str(logs.output))

    def test_acceptance_requires_message_id_and_never_logs_recipient(self):
        with patch.object(settings, "resend_api_key", "fixture"):
            for response, expected in (({}, False), (None, False), ({"id": "fixture-id"}, True)):
                with patch.object(self.module.resend.Emails, "send", return_value=response), self.assertLogs(self.module.logger, level="INFO") as logs:
                    self.assertEqual(self.send(), expected)
                    self.assertNotIn("private@example", str(logs.output))
            with patch.object(self.module.resend.Emails, "send", side_effect=RuntimeError("Private body")), self.assertLogs(self.module.logger) as logs:
                self.assertFalse(self.send()); self.assertNotIn("Private body", str(logs.output))
