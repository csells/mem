import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StatementTests(unittest.TestCase):
    def run_request(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def check_request(self, request, expected):
        self.assertEqual(self.run_request(request), expected)

    def line(self, **overrides):
        line = {"line_id": "L-1", "account_id": "A", "subscription_id": "S",
                "service_on": "2026-04-15", "charge_cents": 19999}
        line.update(overrides)
        return line

    def test_release_2_empty_statement(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": []},
            {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0})

    def test_omitted_release_empty_selects_current(self):
        self.check_request(
            {"command": "statement", "lines": []},
            {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0})

    def test_release_2_one_line(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [self.line()]},
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000,
             "lines": [{"line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000}]})

    def test_release_2_priority_and_input_order(self):
        # Largest charge first, equal charges by increasing line_id: L-2 takes
        # 2250 of the 3000-cent cap, L-3 the remaining 750, L-1 nothing. The
        # response keeps the input order rather than the priority order.
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                self.line(line_id="L-3", charge_cents=15000),
                self.line(line_id="L-1", charge_cents=10000),
                self.line(line_id="L-2", charge_cents=15000),
            ]},
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 37000,
             "lines": [
                 {"line_id": "L-3", "credit_cents": 750, "amount_due_cents": 14250},
                 {"line_id": "L-1", "credit_cents": 0, "amount_due_cents": 10000},
                 {"line_id": "L-2", "credit_cents": 2250, "amount_due_cents": 12750},
             ]})

    def test_release_2_independent_caps_per_subscription_of_one_account(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                self.line(line_id="L-1", account_id="A", subscription_id="S1", charge_cents=30000),
                self.line(line_id="L-2", account_id="A", subscription_id="S2", charge_cents=30000),
            ]},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000,
             "lines": [
                 {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 27000},
                 {"line_id": "L-2", "credit_cents": 3000, "amount_due_cents": 27000},
             ]})

    def test_release_2_credit_floors_below_seven_cents(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                self.line(charge_cents=5),
                self.line(line_id="L-2", charge_cents=6),
            ]},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 11,
             "lines": [
                 {"line_id": "L-1", "credit_cents": 0, "amount_due_cents": 5},
                 {"line_id": "L-2", "credit_cents": 0, "amount_due_cents": 6},
             ]})

    def test_release_1_empty_statement(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": []},
            {"release": "1.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0})

    def test_release_1_priority_and_input_order(self):
        # Earliest service_on first, equal dates by increasing line_id: L-2,
        # then L-3, then L-1, all sharing one 2400-cent account cap.
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": [
                self.line(line_id="L-1", subscription_id="S",
                          service_on="2026-04-16", charge_cents=20000),
                self.line(line_id="L-2", subscription_id="S2",
                          service_on="2026-04-15", charge_cents=10000),
                self.line(line_id="L-3", subscription_id="S",
                          service_on="2026-04-15", charge_cents=5000),
            ]},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 32600,
             "lines": [
                 {"line_id": "L-1", "credit_cents": 900, "amount_due_cents": 19100},
                 {"line_id": "L-2", "credit_cents": 1000, "amount_due_cents": 9000},
                 {"line_id": "L-3", "credit_cents": 500, "amount_due_cents": 4500},
             ]})

    def test_overall_amounts_equal_total_command(self):
        for release, lines in (
            ("2.0", [
                self.line(line_id="L-3", charge_cents=15000),
                self.line(line_id="L-1", charge_cents=10000),
                self.line(line_id="L-2", charge_cents=15000),
            ]),
            ("1.0", [
                self.line(line_id="L-1", service_on="2026-04-16", charge_cents=20000),
                self.line(line_id="L-2", service_on="2026-04-15", charge_cents=10000),
            ]),
        ):
            statement = self.run_request({"command": "statement", "release": release, "lines": lines})
            total = self.run_request({"command": "total", "release": release, "lines": lines})
            self.assertEqual(statement["credit_cents"], total["credit_cents"])
            self.assertEqual(statement["amount_due_cents"], total["amount_due_cents"])
            self.assertEqual(statement["credit_cents"],
                             sum(line["credit_cents"] for line in statement["lines"]))

    def test_unsupported_release(self):
        self.check_request(
            {"command": "statement", "release": "9.9", "lines": []},
            {"error": "unsupported_release"})


if __name__ == "__main__":
    unittest.main()
