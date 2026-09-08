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

    def test_quote_uses_release_1_by_default(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-low",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2020-01-01",
                    "charge_cents": 109,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-low",
                "credit_cents": 10,
                "amount_due_cents": 99,
            },
        )

    def test_quote_caps_single_line_credit(self):
        self.check_request(
            {
                "command": "quote",
                "release": "1.0",
                "line": {
                    "line_id": "L-cap",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2099-12-31",
                    "charge_cents": 50000,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-cap",
                "credit_cents": 2400,
                "amount_due_cents": 47600,
            },
        )
