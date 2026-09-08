import json
import subprocess
import sys
import unittest

from test_total import ROOT, line


class StatementTests(unittest.TestCase):
    def request(self, command, lines, release):
        payload = {"command": command, "lines": lines}
        if release is not None:
            payload["release"] = release
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py")],
            input=json.dumps(payload), text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def check_statement(self, lines, credits):
        expected_lines = [
            {"line_id": item["line_id"], "credit_cents": credit,
             "amount_due_cents": item["charge_cents"] - credit}
            for item, credit in zip(lines, credits)
        ]
        for release in (None, "2.0"):
            with self.subTest(release=release):
                response = self.request("statement", lines, release)
                totals = {
                    "release": "2.0", "credit_cents": sum(credits),
                    "amount_due_cents": sum(item["charge_cents"] for item in lines) - sum(credits),
                }
                self.assertEqual(response, {**totals, "lines": expected_lines})
                self.assertEqual(self.request("total", lines, release), totals)
                for item in [response, *response["lines"]]:
                    self.assertIs(type(item["credit_cents"]), int)
                    self.assertIs(type(item["amount_due_cents"]), int)

    def test_empty_and_single_line(self):
        self.check_statement([], [])
        self.check_statement([line("L-1", "A", "S", 19999)], [2999])

    def test_priority_partial_credit_and_exhausted_cap(self):
        lines = [
            line("small", "A", "S", 5000, "2020-01-01"),
            line("medium", "A", "S", 10000, "2020-01-01"),
            line("large", "A", "S", 15000, "2099-12-31"),
        ]
        self.check_statement(lines, [0, 750, 2250])
        self.check_statement(list(reversed(lines)), [2250, 750, 0])

    def test_unicode_ties_and_independent_groups(self):
        self.check_statement([
            line("😀", "A", "S", 15000, "2020-01-01"),
            line("é", "A", "S", 15000),
            line("a", "A", "S", 15000, "2099-12-31"),
            line("other-sub", "A", "T", 20000),
            line("other-account", "B", "S", 20000),
        ], [0, 750, 2250, 3000, 3000])

    def test_rounding_zero_and_large_integers(self):
        self.check_statement([
            line("floor-1", "A", "S", 19),
            line("floor-2", "A", "S", 19),
            line("sub-cent", "A", "S", 6),
            line("zero", "A", "S", 0),
            line("huge", "B", "S", 10**30 + 9),
            line("remainder", "C", "S", 7),
            line("near-cap", "C", "S", 19999),
        ], [2, 2, 0, 0, 3000, 1, 2999])
