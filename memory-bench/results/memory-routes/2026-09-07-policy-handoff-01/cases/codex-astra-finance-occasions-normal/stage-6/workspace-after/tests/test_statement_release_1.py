import copy
import itertools
import unittest

from main import handle
from test_total import line


class Release1StatementTests(unittest.TestCase):
    def check_statement(self, lines, credits):
        original = copy.deepcopy(lines)
        request = {"command": "statement", "release": "1.0", "lines": lines}
        totals = {
            "release": "1.0",
            "credit_cents": sum(credits),
            "amount_due_cents": sum(item["charge_cents"] for item in lines)
            - sum(credits),
        }
        self.assertEqual(handle(request), {
            **totals,
            "lines": [
                {"line_id": item["line_id"], "credit_cents": credit,
                 "amount_due_cents": item["charge_cents"] - credit}
                for item, credit in zip(lines, credits)
            ],
        })
        self.assertEqual(handle({**request, "command": "total"}), totals)
        self.assertEqual(lines, original)

    def test_empty_and_single_line_boundaries(self):
        self.check_statement([], [])
        for charge, credit in ((0, 0), (9, 0), (10, 1), (19999, 1999),
                               (23999, 2399), (24000, 2400),
                               (24010, 2400), (10**20, 2400)):
            with self.subTest(charge=charge):
                self.check_statement([line("L-1", "A", "S", charge)], [credit])

    def test_date_priority_across_subscriptions_partial_and_exhausted_cap(self):
        lines = [line("a-late", "A", "S", 30000, "2099-12-31"),
                 line("z-early", "A", "T", 10000, "2020-01-01"),
                 line("middle", "A", "S", 20000, "2026-04-15")]
        expected = {"a-late": 0, "z-early": 1000, "middle": 1400}
        for order in itertools.permutations(lines):
            self.check_statement(list(order), [expected[x["line_id"]] for x in order])
        # A subsequent request starts with a fresh account cap.
        self.check_statement([lines[0]], [2400])

    def test_equal_dates_use_unicode_id_priority_regardless_of_charge(self):
        lines = [line("Ω", "A", "S", 30000),
                 line("é", "A", "T", 20000),
                 line("Z", "A", "S", 10000)]
        self.check_statement(lines, [0, 1400, 1000])
        self.check_statement(list(reversed(lines)), [1000, 1400, 0])

    def test_accounts_have_independent_caps_with_same_subscription_id(self):
        self.check_statement([
            line("1", "A", "S", 10000),
            line("2", "B", "S", 30000),
            line("3", "A", "T", 20000),
            line("4", "C", "S", 19),
        ], [1000, 2400, 1400, 1])

    def test_floor_rounding_is_per_line_and_date_endpoints_are_included(self):
        self.check_statement([
            line("1", "A", "S", 19, "2020-01-01"),
            line("2", "A", "S", 19, "2099-12-31"),
            line("3", "A", "T", 9),
            line("4", "A", "T", 0),
        ], [1, 1, 0, 0])
