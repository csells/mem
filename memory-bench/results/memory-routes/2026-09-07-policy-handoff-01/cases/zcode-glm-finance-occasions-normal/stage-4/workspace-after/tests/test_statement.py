import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account_id, subscription_id, service_on, charge_cents):
    return {
        "line_id": line_id,
        "account_id": account_id,
        "subscription_id": subscription_id,
        "service_on": service_on,
        "charge_cents": charge_cents,
    }


class StatementTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_statement_empty_statement(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": []},
            {"release": "1.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_statement_omitted_release_selects_current_agreement(self):
        self.check_request(
            {"command": "statement", "lines": []},
            {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_statement_one_line(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                line("L-1", "A", "S", "2026-04-15", 19999),
            ]},
            {"release": "2.0", "lines": [
                {"line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000},
            ], "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_statement_release_2_priority_favors_largest_charge(self):
        # Same (account_id, subscription_id) group: the 20000-cent line is
        # credited first and exhausts the 3000-cent cap.
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                line("L-1", "A", "S", "2026-04-01", 10000),
                line("L-2", "A", "S", "2026-04-02", 20000),
            ]},
            {"release": "2.0", "lines": [
                {"line_id": "L-1", "credit_cents": 0, "amount_due_cents": 10000},
                {"line_id": "L-2", "credit_cents": 3000, "amount_due_cents": 17000},
            ], "credit_cents": 3000, "amount_due_cents": 27000},
        )

    def test_statement_release_2_equal_charges_use_increasing_line_id(self):
        # Uncapped credit is 3000 each; the cap goes entirely to L-1.
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                line("L-2", "A", "S", "2026-04-01", 20000),
                line("L-1", "A", "S", "2026-04-02", 20000),
            ]},
            {"release": "2.0", "lines": [
                {"line_id": "L-2", "credit_cents": 0, "amount_due_cents": 20000},
                {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 17000},
            ], "credit_cents": 3000, "amount_due_cents": 37000},
        )

    def test_statement_release_2_keeps_input_line_order(self):
        # Group cap split across lines; the response lists them as supplied,
        # not in credit-priority order.
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                line("L-2", "A", "S", "2026-04-02", 10000),
                line("L-1", "A", "S", "2026-04-01", 20000),
            ]},
            {"release": "2.0", "lines": [
                {"line_id": "L-2", "credit_cents": 0, "amount_due_cents": 10000},
                {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 17000},
            ], "credit_cents": 3000, "amount_due_cents": 27000},
        )

    def test_statement_release_2_caps_subscription_groups_independently(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [
                line("L-1", "A", "S1", "2026-04-01", 20000),
                line("L-2", "A", "S2", "2026-04-01", 20000),
                line("L-3", "B", "S1", "2026-04-01", 20000),
            ]},
            {"release": "2.0", "lines": [
                {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 17000},
                {"line_id": "L-2", "credit_cents": 3000, "amount_due_cents": 17000},
                {"line_id": "L-3", "credit_cents": 3000, "amount_due_cents": 17000},
            ], "credit_cents": 9000, "amount_due_cents": 51000},
        )

    def test_statement_release_1_priority_favors_earliest_service_date(self):
        # One per-account cap: the line serviced first takes the full 2400.
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": [
                line("L-1", "A", "S", "2026-04-02", 30000),
                line("L-2", "A", "S", "2026-04-01", 30000),
            ]},
            {"release": "1.0", "lines": [
                {"line_id": "L-1", "credit_cents": 0, "amount_due_cents": 30000},
                {"line_id": "L-2", "credit_cents": 2400, "amount_due_cents": 27600},
            ], "credit_cents": 2400, "amount_due_cents": 57600},
        )

    def test_statement_release_1_splits_the_cap_within_an_account(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": [
                line("L-1", "A", "S1", "2026-04-01", 15000),
                line("L-2", "A", "S2", "2026-04-02", 15000),
            ]},
            {"release": "1.0", "lines": [
                {"line_id": "L-1", "credit_cents": 1500, "amount_due_cents": 13500},
                {"line_id": "L-2", "credit_cents": 900, "amount_due_cents": 14100},
            ], "credit_cents": 2400, "amount_due_cents": 27600},
        )

    def test_statement_overall_amounts_equal_total(self):
        lines = [
            line("L-1", "A", "S1", "2026-04-01", 30000),
            line("L-2", "A", "S1", "2026-04-02", 10000),
            line("L-3", "B", "S1", "2026-04-03", 19999),
        ]
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps({"command": "statement", "release": "2.0", "lines": lines}),
                             text=True, capture_output=True, check=True)
        statement = json.loads(got.stdout)
        self.assertEqual(statement["credit_cents"],
                         sum(l["credit_cents"] for l in statement["lines"]))
        self.assertEqual(statement["amount_due_cents"],
                         sum(l["amount_due_cents"] for l in statement["lines"]))
        self.assertEqual(statement["credit_cents"] + statement["amount_due_cents"],
                         sum(l["charge_cents"] for l in lines))

    def test_statement_unsupported_release(self):
        self.check_request(
            {"command": "statement", "release": "9.9", "lines": []},
            {"error": "unsupported_release"},
        )


if __name__ == "__main__":
    unittest.main()
