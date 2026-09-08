import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StatementTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def run_command(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

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

    def test_issue_example_line(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": [self.line()]},
            {
                "release": "2.0",
                "credit_cents": 2999,
                "amount_due_cents": 17000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000}
                ],
            },
        )

    def test_empty_statement(self):
        self.check_request(
            {"command": "statement", "release": "2.0", "lines": []},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0, "lines": []},
        )

    def test_omitted_release_selects_current(self):
        self.check_request(
            {"command": "statement", "lines": [self.line()]},
            {
                "release": "2.0",
                "credit_cents": 2999,
                "amount_due_cents": 17000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000}
                ],
            },
        )

    def test_preserves_input_line_order(self):
        lines = [
            self.line(line_id="L-2", charge_cents=10000),
            self.line(line_id="L-1", charge_cents=5000),
        ]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 2250,
                "amount_due_cents": 12750,
                "lines": [
                    {"line_id": "L-2", "credit_cents": 1500, "amount_due_cents": 8500},
                    {"line_id": "L-1", "credit_cents": 750, "amount_due_cents": 4250},
                ],
            },
        )

    def test_largest_charge_first_assigns_cap_before_smaller_lines(self):
        lines = [
            self.line(line_id="L-3", charge_cents=10000, service_on="2026-04-01"),
            self.line(line_id="L-1", charge_cents=10000, service_on="2026-04-02"),
            self.line(line_id="L-2", charge_cents=19999, service_on="2026-04-03"),
        ]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 3000,
                "amount_due_cents": 36999,
                "lines": [
                    {"line_id": "L-3", "credit_cents": 0, "amount_due_cents": 10000},
                    {"line_id": "L-1", "credit_cents": 1, "amount_due_cents": 9999},
                    {"line_id": "L-2", "credit_cents": 2999, "amount_due_cents": 17000},
                ],
            },
        )

    def test_equal_charges_assign_remaining_cap_by_line_id_code_point_order(self):
        lines = [
            self.line(line_id="L-b", charge_cents=11000),
            self.line(line_id="L-a", charge_cents=11000),
        ]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 3000,
                "amount_due_cents": 19000,
                "lines": [
                    {"line_id": "L-b", "credit_cents": 1350, "amount_due_cents": 9650},
                    {"line_id": "L-a", "credit_cents": 1650, "amount_due_cents": 9350},
                ],
            },
        )

    def test_cap_independent_across_subscriptions_of_one_account(self):
        lines = [
            self.line(line_id="L-1", subscription_id="S1", charge_cents=20000),
            self.line(line_id="L-2", subscription_id="S2", charge_cents=20000),
        ]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 6000,
                "amount_due_cents": 34000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 17000},
                    {"line_id": "L-2", "credit_cents": 3000, "amount_due_cents": 17000},
                ],
            },
        )

    def test_uncapped_lines_each_round_down(self):
        lines = [self.line(line_id=f"L-{i}", charge_cents=1234) for i in range(3)]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 555,
                "amount_due_cents": 3147,
                "lines": [
                    {"line_id": "L-0", "credit_cents": 185, "amount_due_cents": 1049},
                    {"line_id": "L-1", "credit_cents": 185, "amount_due_cents": 1049},
                    {"line_id": "L-2", "credit_cents": 185, "amount_due_cents": 1049},
                ],
            },
        )

    def test_overall_amounts_equal_total_for_same_input(self):
        lines = [
            self.line(line_id="L-1", subscription_id="S1", charge_cents=19999),
            self.line(line_id="L-2", subscription_id="S1", charge_cents=10000),
            self.line(line_id="L-3", subscription_id="S2", charge_cents=1234),
        ]
        statement = self.run_command({"command": "statement", "lines": lines})
        total = self.run_command({"command": "total", "lines": lines})
        self.assertEqual(statement["credit_cents"], total["credit_cents"])
        self.assertEqual(statement["amount_due_cents"], total["amount_due_cents"])
        self.assertEqual(sum(line["credit_cents"] for line in statement["lines"]),
                         statement["credit_cents"])
        self.assertEqual(sum(line["amount_due_cents"] for line in statement["lines"]),
                         statement["amount_due_cents"])

    def test_unsupported_release(self):
        self.check_request(
            {"command": "statement", "release": "3.0", "lines": [self.line()]},
            {"error": "unsupported_release"},
        )

    def test_release_1_not_offered_for_statement(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": [self.line()]},
            {"error": "unsupported_release"},
        )

    def test_response_has_exactly_specified_keys(self):
        got = self.run_command({"command": "statement", "lines": [self.line()]})
        self.assertEqual(set(got), {"release", "lines", "credit_cents", "amount_due_cents"})
        self.assertEqual(set(got["lines"][0]),
                         {"line_id", "credit_cents", "amount_due_cents"})
