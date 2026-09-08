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

    def test_quote_release_1_0(self):
        line = {"line_id": "L-1", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 19999}
        expected = {"release": "1.0", "line_id": "L-1",
                    "credit_cents": 1999, "amount_due_cents": 18000}
        self.check_request({"command": "quote", "release": "1.0", "line": line}, expected)

    def test_quote_omitted_release_selects_current(self):
        line = {"line_id": "L-2", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 19999}
        expected = {"release": "1.0", "line_id": "L-2",
                    "credit_cents": 1999, "amount_due_cents": 18000}
        self.check_request({"command": "quote", "line": line}, expected)

    def test_quote_credit_capped_at_2400(self):
        line = {"line_id": "L-3", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 25000}
        expected = {"release": "1.0", "line_id": "L-3",
                    "credit_cents": 2400, "amount_due_cents": 22600}
        self.check_request({"command": "quote", "release": "1.0", "line": line}, expected)

    def test_quote_zero_charge(self):
        line = {"line_id": "L-4", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 0}
        expected = {"release": "1.0", "line_id": "L-4",
                    "credit_cents": 0, "amount_due_cents": 0}
        self.check_request({"command": "quote", "release": "1.0", "line": line}, expected)
