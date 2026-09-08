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

    def test_quote_defaults_to_current_release(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-1",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-04-15",
                    "charge_cents": 19999,
                },
            },
            {
                "release": "1.0",
                "credit_cents": 1999,
                "amount_due_cents": 18000,
                "line_id": "L-1",
            },
        )

    def test_empty_statement_total(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_total_caps_credits_by_account(self):
        lines = [
            {
                "line_id": "later",
                "account_id": "A",
                "subscription_id": "S-1",
                "service_on": "2026-02-01",
                "charge_cents": 20000,
            },
            {
                "line_id": "earlier",
                "account_id": "A",
                "subscription_id": "S-2",
                "service_on": "2026-01-01",
                "charge_cents": 10000,
            },
            {
                "line_id": "other-account",
                "account_id": "B",
                "subscription_id": "S-1",
                "service_on": "2026-03-01",
                "charge_cents": 5000,
            },
        ]
        self.check_request(
            {"command": "total", "lines": lines},
            {
                "release": "1.0",
                "credit_cents": 2900,
                "amount_due_cents": 32100,
            },
        )
