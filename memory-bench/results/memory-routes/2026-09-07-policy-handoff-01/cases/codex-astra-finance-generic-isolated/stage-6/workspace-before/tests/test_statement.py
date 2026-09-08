import copy
import itertools
import unittest

from main import handle
from test_total import line


class StatementTests(unittest.TestCase):
    def check_statement(self, lines, credits):
        original = copy.deepcopy(lines)
        expected_lines = [
            {"line_id": charge["line_id"], "credit_cents": credit,
             "amount_due_cents": charge["charge_cents"] - credit}
            for charge, credit in zip(lines, credits)
        ]
        self.assertEqual(len(lines), len(credits))
        for release in ({}, {"release": "2.0"}):
            with self.subTest(release=release):
                response = handle({"command": "statement", "lines": lines, **release})
                self.assertEqual(response, {
                    "release": "2.0", "lines": expected_lines,
                    "credit_cents": sum(credits),
                    "amount_due_cents": sum(item["charge_cents"] for item in lines) - sum(credits),
                })
                self.assertEqual(
                    {key: value for key, value in response.items() if key != "lines"},
                    handle({"command": "total", "lines": lines, **release}),
                )
                self.assertEqual(lines, original)

    def test_empty_zero_and_single_line(self):
        self.check_statement([], [])
        for charge, credit in ((0, 0), (7, 1), (19999, 2999), (20000, 3000),
                               (10**100 + 19, 3000)):
            with self.subTest(charge=charge):
                self.check_statement([line("L-1", "A", "S", charge)], [credit])

    def test_charge_priority_partial_credit_and_exhaustion(self):
        lines = [line("first", "A", "S", 10000, "2020-01-01"),
                 line("largest", "A", "S", 15000, "2099-12-31"),
                 line("smallest", "A", "S", 1000)]
        credits = {"first": 750, "largest": 2250, "smallest": 0}
        for permutation in itertools.permutations(lines):
            self.check_statement(list(permutation), [credits[item["line_id"]] for item in permutation])

    def test_equal_charges_use_unicode_id_order_before_dates(self):
        self.check_statement([
            line("é", "A", "S", 10000, "2020-01-01"),
            line("a", "A", "S", 10000),
            line("Z", "A", "S", 10000, "2099-12-31"),
        ], [0, 1500, 1500])

    def test_caps_are_independent_per_account_subscription_pair(self):
        self.check_statement([
            line("A-S-small", "A", "S", 10000),
            line("B-S", "B", "S", 30000),
            line("A-T", "A", "T", 30000),
            line("A-S-large", "A", "S", 30000),
        ], [0, 3000, 3000, 3000])

    def test_round_each_line_before_allocation(self):
        self.check_statement([line("1", "A", "S", 19),
                              line("2", "A", "S", 19)], [2, 2])
        self.check_statement([line("small", "A", "S", 7),
                              line("large", "A", "S", 19999),
                              line("zero", "A", "S", 0)], [1, 2999, 0])


if __name__ == "__main__":
    unittest.main()
