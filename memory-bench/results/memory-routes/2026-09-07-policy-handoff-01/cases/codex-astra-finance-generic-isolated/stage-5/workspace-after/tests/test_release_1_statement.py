import copy
import itertools
import unittest

from main import handle
from test_total import line


class ReleaseOneStatementTests(unittest.TestCase):
    def check_statement(self, lines, credits):
        original = copy.deepcopy(lines)
        self.assertEqual(len(lines), len(credits))
        response = handle({"command": "statement", "release": "1.0", "lines": lines})
        self.assertEqual(response, {
            "release": "1.0",
            "lines": [
                {"line_id": charge["line_id"], "credit_cents": credit,
                 "amount_due_cents": charge["charge_cents"] - credit}
                for charge, credit in zip(lines, credits)
            ],
            "credit_cents": sum(credits),
            "amount_due_cents": sum(item["charge_cents"] for item in lines) - sum(credits),
        })
        self.assertEqual(
            {key: value for key, value in response.items() if key != "lines"},
            handle({"command": "total", "release": "1.0", "lines": lines}),
        )
        self.assertEqual(lines, original)

    def test_empty_zero_and_single_line(self):
        self.check_statement([], [])
        for charge, credit in ((0, 0), (9, 0), (19, 1), (19999, 1999),
                               (24000, 2400), (10**100 + 19, 2400)):
            with self.subTest(charge=charge):
                self.check_statement([line("L-1", "A", "S", charge)], [credit])

    def test_date_priority_partial_credit_and_exhaustion_across_subscriptions(self):
        lines = [line("a-latest", "A", "S", 30000, "2099-12-31"),
                 line("z-earliest", "A", "T", 10000, "2020-01-01"),
                 line("middle", "A", "S", 20000, "2026-04-15")]
        credits = {"a-latest": 0, "z-earliest": 1000, "middle": 1400}
        for permutation in itertools.permutations(lines):
            self.check_statement(list(permutation), [credits[item["line_id"]] for item in permutation])

    def test_same_date_uses_unicode_id_order_before_charge(self):
        self.check_statement([
            line("é", "A", "S", 30000),
            line("a", "A", "T", 20000),
            line("Z", "A", "S", 10000),
        ], [0, 1400, 1000])

    def test_accounts_have_independent_caps_with_same_subscription_id(self):
        self.check_statement([
            line("A-S", "A", "S", 30000),
            line("B-S", "B", "S", 30000),
            line("A-T", "A", "T", 30000),
        ], [2400, 2400, 0])

    def test_round_each_line_before_allocation(self):
        self.check_statement([line("1", "A", "S", 19),
                              line("2", "A", "S", 19)], [1, 1])
        self.check_statement([line("3", "A", "S", 19),
                              line("2", "A", "T", 19),
                              line("1", "A", "S", 23999)], [0, 1, 2399])


if __name__ == "__main__":
    unittest.main()
