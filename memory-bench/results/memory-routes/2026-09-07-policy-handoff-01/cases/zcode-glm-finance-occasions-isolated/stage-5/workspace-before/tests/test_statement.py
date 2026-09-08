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
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def check_statement(self, lines, release=None):
        request = {"command": "statement", "lines": lines}
        if release is not None:
            request["release"] = release
        return self.run_cli(request)

    def test_empty_statement_release_1_0(self):
        got = self.check_statement([], release="1.0")
        self.assertEqual(got, {"release": "1.0", "lines": [],
                               "credit_cents": 0, "amount_due_cents": 0})

    def test_empty_statement_release_2_0(self):
        got = self.check_statement([], release="2.0")
        self.assertEqual(got, {"release": "2.0", "lines": [],
                               "credit_cents": 0, "amount_due_cents": 0})

    def test_omitted_release_selects_current(self):
        got = self.check_statement([])
        self.assertEqual(got, {"release": "2.0", "lines": [],
                               "credit_cents": 0, "amount_due_cents": 0})

    def test_one_line_matches_public_example(self):
        got = self.check_statement([line("L-1", "A", "S", "2026-04-15", 19999)])
        self.assertEqual(got, {"release": "2.0", "credit_cents": 2999,
                               "amount_due_cents": 17000,
                               "lines": [{"line_id": "L-1", "credit_cents": 2999,
                                          "amount_due_cents": 17000}]})

    # Release 1.0 agreement, retained for explicit requests.

    def test_release_1_0_per_line_priority_earliest_date_then_line_id(self):
        lines = [
            line("L-b2", "B", "S", "2026-05-05", 30000),
            line("L-b1", "B", "S", "2026-05-05", 30000),
            line("L-b0", "B", "S", "2026-04-01", 1000),
        ]
        # L-b0 (earliest) 100; L-b1 then L-b2 tie on date, split by line_id:
        # L-b1 takes the remaining 2300, L-b2 gets 0. Input order is preserved.
        got = self.check_statement(lines, release="1.0")
        self.assertEqual(got, {
            "release": "1.0",
            "lines": [
                {"line_id": "L-b2", "credit_cents": 0, "amount_due_cents": 30000},
                {"line_id": "L-b1", "credit_cents": 2300, "amount_due_cents": 27700},
                {"line_id": "L-b0", "credit_cents": 100, "amount_due_cents": 900},
            ],
            "credit_cents": 2400,
            "amount_due_cents": 58600,
        })

    # Release 2.0 agreement, current as of its adoption.

    def test_release_2_0_per_line_priority_largest_charge_then_line_id(self):
        lines = [
            line("L-1", "A", "S", "2026-05-05", 25000),
            line("L-2", "A", "S", "2026-04-20", 25000),
            line("L-3", "A", "S", "2026-01-01", 10000),
            line("L-4", "A", "T", "2026-04-15", 25000),
            line("L-5", "B", "S", "2026-04-15", 20000),
        ]
        # (A,S): L-1 and L-2 tie at 25000, L-1 first by line_id, takes the
        # whole 3000 cap despite L-3's earlier service date; L-4 in (A,T) and
        # L-5 in (B,S) have independent caps.
        got = self.check_statement(lines, release="2.0")
        self.assertEqual(got, {
            "release": "2.0",
            "lines": [
                {"line_id": "L-1", "credit_cents": 3000, "amount_due_cents": 22000},
                {"line_id": "L-2", "credit_cents": 0, "amount_due_cents": 25000},
                {"line_id": "L-3", "credit_cents": 0, "amount_due_cents": 10000},
                {"line_id": "L-4", "credit_cents": 3000, "amount_due_cents": 22000},
                {"line_id": "L-5", "credit_cents": 3000, "amount_due_cents": 17000},
            ],
            "credit_cents": 9000,
            "amount_due_cents": 96000,
        })

    def test_release_2_0_later_line_receives_only_remaining_credit(self):
        lines = [
            line("L-1", "A", "S", "2026-04-01", 19400),
            line("L-2", "A", "S", "2026-04-02", 1000),
        ]
        # L-1 takes 2910, leaving 90 of the 3000 cap; L-2's uncapped 150
        # exceeds that, so it receives only the remaining 90.
        got = self.check_statement(lines, release="2.0")
        self.assertEqual(got["lines"], [
            {"line_id": "L-1", "credit_cents": 2910, "amount_due_cents": 16490},
            {"line_id": "L-2", "credit_cents": 90, "amount_due_cents": 910},
        ])

    def test_overall_amounts_equal_total_for_same_input(self):
        lines = [
            line("L-1", "A", "S1", "2026-04-01", 20000),
            line("L-2", "A", "S2", "2026-04-20", 20000),
        ]
        for release in ("1.0", "2.0"):
            with self.subTest(release=release):
                statement = self.check_statement(lines, release=release)
                total = self.run_cli({"command": "total", "release": release,
                                      "lines": lines})
                self.assertEqual(statement["credit_cents"], total["credit_cents"])
                self.assertEqual(statement["amount_due_cents"], total["amount_due_cents"])

    def test_unsupported_release(self):
        got = self.run_cli({"command": "statement", "release": "0.9", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})
