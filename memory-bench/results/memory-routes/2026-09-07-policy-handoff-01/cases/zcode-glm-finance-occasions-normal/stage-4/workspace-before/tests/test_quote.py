import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

LINE = {
    "line_id": "L-1",
    "account_id": "A",
    "subscription_id": "S",
    "service_on": "2026-04-15",
    "charge_cents": 19999,
}


class QuoteTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_quote_explicit_release(self):
        self.check_request(
            {"command": "quote", "release": "1.0", "line": dict(LINE)},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_quote_omitted_release_selects_current_agreement(self):
        self.check_request(
            {"command": "quote", "line": dict(LINE)},
            {"release": "2.0", "line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_quote_caps_credit_at_2400(self):
        line = dict(LINE, charge_cents=30000)
        self.check_request(
            {"command": "quote", "release": "1.0", "line": line},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 2400, "amount_due_cents": 27600},
        )

    def test_quote_rounds_credit_down(self):
        line = dict(LINE, charge_cents=15)
        self.check_request(
            {"command": "quote", "release": "1.0", "line": line},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 1, "amount_due_cents": 14},
        )

    def test_quote_zero_charge(self):
        line = dict(LINE, charge_cents=0)
        self.check_request(
            {"command": "quote", "line": line},
            {"release": "2.0", "line_id": "L-1", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_quote_release_2_caps_credit_at_3000(self):
        line = dict(LINE, charge_cents=30000)
        self.check_request(
            {"command": "quote", "release": "2.0", "line": line},
            {"release": "2.0", "line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 27000},
        )

    def test_quote_release_2_rounds_credit_down(self):
        line = dict(LINE, charge_cents=15)
        self.check_request(
            {"command": "quote", "release": "2.0", "line": line},
            {"release": "2.0", "line_id": "L-1", "credit_cents": 2, "amount_due_cents": 13},
        )

    def test_quote_unsupported_release(self):
        self.check_request(
            {"command": "quote", "release": "9.9", "line": dict(LINE)},
            {"error": "unsupported_release"},
        )


if __name__ == "__main__":
    unittest.main()
