import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TotalTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def line(self, **overrides):
        line = {"line_id": "L-1", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 19999}
        line.update(overrides)
        return line

    def test_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_omitted_release_selects_current(self):
        self.check_request(
            {"command": "total", "lines": [self.line()]},
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000})

    def test_cap_shared_across_lines_of_one_account(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", charge_cents=20000),
                self.line(line_id="L-2", charge_cents=10000),
            ]},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 27600})

    def test_independent_caps_per_account(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", account_id="A", charge_cents=20000),
                self.line(line_id="L-2", account_id="B", charge_cents=20000),
            ]},
            {"release": "1.0", "credit_cents": 4000, "amount_due_cents": 36000})

    def test_same_subscription_id_under_different_accounts(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S", charge_cents=30000),
                self.line(line_id="L-2", account_id="B", subscription_id="S", charge_cents=30000),
            ]},
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200})

    def test_several_lines_of_one_subscription(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", charge_cents=5000),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=5000),
                self.line(line_id="L-3", service_on="2026-04-17", charge_cents=5000),
            ]},
            {"release": "1.0", "credit_cents": 1500, "amount_due_cents": 13500})

    def test_credit_floors_below_ten_cents(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(charge_cents=5),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=5),
            ]},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 10})

    def test_zero_charges(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(charge_cents=0),
                self.line(line_id="L-2", account_id="B", service_on="2026-04-16", charge_cents=0),
            ]},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_unsupported_release(self):
        self.check_request(
            {"command": "total", "release": "9.9", "lines": []},
            {"error": "unsupported_release"})


if __name__ == "__main__":
    unittest.main()
