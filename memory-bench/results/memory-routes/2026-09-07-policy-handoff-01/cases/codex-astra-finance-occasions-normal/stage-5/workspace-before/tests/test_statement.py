import copy
import itertools
import unittest

from main import handle
from test_total import line


class StatementTests(unittest.TestCase):
    def check_statement(self, lines, credits):
        original = copy.deepcopy(lines)
        for release in (None, "2.0"):
            with self.subTest(release=release):
                request = {"command": "statement", "lines": lines}
                if release is not None:
                    request["release"] = release
                total = {
                    "release": "2.0",
                    "credit_cents": sum(credits),
                    "amount_due_cents": sum(
                        item["charge_cents"] for item in lines
                    ) - sum(credits),
                }
                self.assertEqual(handle(request), {
                    **total,
                    "lines": [
                        {"line_id": item["line_id"], "credit_cents": credit,
                         "amount_due_cents": item["charge_cents"] - credit}
                        for item, credit in zip(lines, credits)
                    ],
                })
                self.assertEqual(handle({**request, "command": "total"}), total)
                self.assertEqual(lines, original)

    def test_empty_single_line_and_integer_boundaries(self):
        self.check_statement([], [])
        for charge, credit in ((0, 0), (6, 0), (7, 1), (19999, 2999),
                               (20000, 3000), (20007, 3000), (10**20, 3000)):
            with self.subTest(charge=charge):
                self.check_statement([line("L-1", "A", "S", charge)], [credit])

    def test_largest_charge_first_partial_credit_and_exhausted_cap(self):
        lines = [line("small", "A", "S", 5000, "2020-01-01"),
                 line("medium", "A", "S", 10000, "2026-04-15"),
                 line("large", "A", "S", 15000, "2099-12-31")]
        expected = {"small": 0, "medium": 750, "large": 2250}
        for order in itertools.permutations(lines):
            self.check_statement(list(order), [expected[x["line_id"]] for x in order])
        # Each new statement starts with a fresh cap.
        self.check_statement([lines[0]], [750])

    def test_equal_charges_use_unicode_id_order_not_dates_or_input(self):
        lines = [line("é", "A", "S", 15000, "2020-01-01"),
                 line("Ω", "A", "S", 15000, "2020-01-01"),
                 line("Z", "A", "S", 15000, "2099-12-31")]
        self.check_statement(lines, [750, 0, 2250])
        self.check_statement(list(reversed(lines)), [2250, 0, 750])

    def test_independent_pair_groups_and_collision_free_ids(self):
        self.check_statement([
            line("1", "A", "S", 10000),
            line("2", "A", "T", 30000),
            line("3", "B", "S", 30000),
            line("4", "A", "S", 15000),
            line("5", "A:B", "C", 30000),
            line("6", "A", "B:C", 30000),
        ], [750, 3000, 3000, 2250, 3000, 3000])

    def test_rounding_is_per_line(self):
        self.check_statement([
            line("1", "A", "S", 6),
            line("2", "A", "S", 6),
            line("3", "A", "S", 19),
            line("4", "A", "S", 0),
        ], [0, 0, 2, 0])
