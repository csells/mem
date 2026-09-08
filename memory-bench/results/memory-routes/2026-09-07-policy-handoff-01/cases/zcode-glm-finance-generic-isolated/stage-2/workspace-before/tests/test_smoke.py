import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_ping(self):
        self.check_request({"command": "ping"}, {"status": "ok", "product": "Meridian Credits"})

    def test_unknown(self):
        self.check_request({"command": "unknown"}, {"error": "unknown_command"})

    def test_quote_example(self):
        self.check_request(
            {
                "command": "quote",
                "release": "1.0",
                "line": {
                    "line_id": "L-1",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-04-15",
                    "charge_cents": 19999,
                },
            },
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000, "line_id": "L-1"},
        )

    def test_quote_without_release_reports_current(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-2",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-05-01",
                    "charge_cents": 50000,
                },
            },
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 47600, "line_id": "L-2"},
        )

    def test_quote_zero_charge(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-0",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-05-01",
                    "charge_cents": 0,
                },
            },
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0, "line_id": "L-0"},
        )
