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

    def test_release_1_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_release_1_one_line(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [self.line()]},
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000})

    def test_release_1_cap_shared_across_lines_of_one_account(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", charge_cents=20000),
                self.line(line_id="L-2", charge_cents=10000),
            ]},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 27600})

    def test_release_1_independent_caps_per_account(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", account_id="A", charge_cents=20000),
                self.line(line_id="L-2", account_id="B", charge_cents=20000),
            ]},
            {"release": "1.0", "credit_cents": 4000, "amount_due_cents": 36000})

    def test_release_1_same_subscription_id_under_different_accounts(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S", charge_cents=30000),
                self.line(line_id="L-2", account_id="B", subscription_id="S", charge_cents=30000),
            ]},
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200})

    def test_release_1_several_lines_of_one_subscription(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(line_id="L-1", charge_cents=5000),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=5000),
                self.line(line_id="L-3", service_on="2026-04-17", charge_cents=5000),
            ]},
            {"release": "1.0", "credit_cents": 1500, "amount_due_cents": 13500})

    def test_release_1_credit_floors_below_ten_cents(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(charge_cents=5),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=5),
            ]},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 10})

    def test_release_1_zero_charges(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                self.line(charge_cents=0),
                self.line(line_id="L-2", account_id="B", service_on="2026-04-16", charge_cents=0),
            ]},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_release_2_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": []},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_release_2_one_line(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [self.line()]},
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000})

    def test_omitted_release_selects_current(self):
        self.check_request(
            {"command": "total", "lines": [self.line()]},
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000})

    def test_release_2_cap_shared_within_one_subscription(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(line_id="L-1", charge_cents=20000),
                self.line(line_id="L-2", charge_cents=10000),
            ]},
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 27000})

    def test_release_2_independent_caps_per_subscription_of_one_account(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S1", charge_cents=20000),
                self.line(line_id="L-2", account_id="A", subscription_id="S2", charge_cents=20000),
            ]},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 34000})

    def test_release_2_same_subscription_id_under_different_accounts(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S", charge_cents=30000),
                self.line(line_id="L-2", account_id="B", subscription_id="S", charge_cents=30000),
            ]},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000})

    def test_release_2_cap_not_shared_across_subscriptions_of_one_account(self):
        # Release 1.0 would share one 2400-cent account cap here; release 2.0
        # gives each (account_id, subscription_id) pair its own 3000 cents.
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S1", charge_cents=30000),
                self.line(line_id="L-2", account_id="A", subscription_id="S2", charge_cents=30000),
            ]},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000})

    def test_release_2_cap_saturates_from_partial_credits(self):
        # Uncapped credits 2250 + 1500 exceed the 3000-cent group cap.
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(line_id="L-1", charge_cents=15000),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=10000),
            ]},
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 22000})

    def test_release_2_credit_floors_below_seven_cents(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(charge_cents=5),
                self.line(line_id="L-2", service_on="2026-04-16", charge_cents=6),
            ]},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 11})

    def test_release_2_zero_charges(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [
                self.line(charge_cents=0),
                self.line(line_id="L-2", account_id="B", service_on="2026-04-16", charge_cents=0),
            ]},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_unsupported_release(self):
        self.check_request(
            {"command": "total", "release": "9.9", "lines": []},
            {"error": "unsupported_release"})


if __name__ == "__main__":
    unittest.main()
