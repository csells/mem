import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_total import line

ROOT = Path(__file__).resolve().parents[1]


class StatementTests(unittest.TestCase):
    def request(self, payload):
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py")],
            input=json.dumps(payload), text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def check_statement(self, lines, expected_credits):
        for release in (None, "2.0"):
            for ordered_lines in (lines, list(reversed(lines))):
                with self.subTest(release=release, lines=ordered_lines):
                    payload = {"command": "statement", "lines": ordered_lines}
                    if release is not None:
                        payload["release"] = release
                    expected_lines = [
                        {"line_id": item["line_id"],
                         "credit_cents": expected_credits[item["line_id"]],
                         "amount_due_cents": item["charge_cents"] -
                         expected_credits[item["line_id"]]}
                        for item in ordered_lines
                    ]
                    totals = {
                        "release": "2.0",
                        "credit_cents": sum(expected_credits.values()),
                        "amount_due_cents": sum(item["charge_cents"] for item in lines)
                        - sum(expected_credits.values()),
                    }
                    self.assertEqual(self.request(payload),
                                     dict(totals, lines=expected_lines))
                    self.assertEqual(self.request(dict(payload, command="total")), totals)

    def test_empty_and_one_line_boundaries(self):
        self.check_statement([], {})
        for charge, credit in ((0, 0), (6, 0), (7, 1), (19999, 2999),
                               (20000, 3000), (10**30 + 9, 3000)):
            self.check_statement([line("L-1", "A", "S", charge)], {"L-1": credit})

    def test_largest_charge_first_with_partial_and_exhausted_credit(self):
        self.check_statement([
            line("a", "A", "S", 10000, "2020-01-01"),
            line("z", "A", "S", 15000, "2099-12-31"),
            line("b", "A", "S", 5000, "2020-01-01"),
        ], {"a": 750, "z": 2250, "b": 0})

    def test_equal_charges_use_unicode_id_order(self):
        self.check_statement([
            line("Ω", "A", "S", 12000, "2020-01-01"),
            line("a", "A", "S", 12000, "2020-01-01"),
            line("Z", "A", "S", 12000, "2099-12-31"),
        ], {"Ω": 0, "a": 1200, "Z": 1800})

    def test_cap_groups_include_both_account_and_subscription(self):
        self.check_statement([
            line("1", "A", "S", 20000),
            line("2", "A", "T", 20000),
            line("3", "B", "S", 20000),
            line("4", "A", "S", 10000),
        ], {"1": 3000, "2": 3000, "3": 3000, "4": 0})

    def test_floor_each_line_and_allocate_last_cent(self):
        self.check_statement([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "A", "S", 6),
            line("4", "B", "S", 19999),
            line("5", "B", "S", 7),
            line("6", "B", "S", 0),
        ], {"1": 2, "2": 2, "3": 0, "4": 2999, "5": 1, "6": 0})
