import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QuoteTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def line(self, **overrides):
        line = {
            "line_id": "L-1",
            "account_id": "A",
            "subscription_id": "S",
            "service_on": "2026-04-15",
            "charge_cents": 19999,
        }
        line.update(overrides)
        return line

    def test_issue_example(self):
        self.check_request(
            {"command": "quote", "release": "1.0", "line": self.line()},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_omitted_release_selects_current(self):
        self.check_request(
            {"command": "quote", "line": self.line()},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_credit_rounds_down(self):
        self.check_request(
            {"command": "quote", "line": self.line(charge_cents=5)},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 0, "amount_due_cents": 5},
        )

    def test_cap_2400(self):
        self.check_request(
            {"command": "quote", "line": self.line(charge_cents=30000)},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 2400, "amount_due_cents": 27600},
        )

    def test_zero_charge(self):
        self.check_request(
            {"command": "quote", "line": self.line(charge_cents=0)},
            {"release": "1.0", "line_id": "L-1", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_response_has_exactly_specified_keys(self):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps({"command": "quote", "line": self.line()}),
                             text=True, capture_output=True, check=True)
        self.assertEqual(set(json.loads(got.stdout)),
                         {"release", "line_id", "credit_cents", "amount_due_cents"})
