import unittest

from main import handle
from test_total import line


class ReleaseTwoTests(unittest.TestCase):
    def check_total(self, lines, credit, due):
        for release in ({}, {"release": "2.0"}):
            with self.subTest(release=release):
                self.assertEqual(
                    handle({"command": "total", "lines": lines, **release}),
                    {"release": "2.0", "credit_cents": credit,
                     "amount_due_cents": due},
                )

    def test_quote_rounding_and_cap(self):
        for charge, credit in ((0, 0), (7, 1), (19999, 2999),
                               (20000, 3000), (30000, 3000)):
            for release in ({}, {"release": "2.0"}):
                with self.subTest(charge=charge, release=release):
                    self.assertEqual(
                        handle({"command": "quote",
                                "line": line("L", "A", "S", charge), **release}),
                        {"release": "2.0", "line_id": "L",
                         "credit_cents": credit, "amount_due_cents": charge - credit},
                    )

    def test_empty_and_zero(self):
        self.check_total([], 0, 0)
        self.check_total([line("zero", "A", "S", 0)], 0, 0)

    def test_shared_cap_and_independent_subscription_pairs(self):
        lines = [line("1", "A", "S", 15000),
                 line("2", "A", "S", 15000),
                 line("3", "A", "T", 30000),
                 line("4", "B", "S", 30000)]
        self.check_total(lines, 9000, 81000)
        self.assertEqual(
            handle({"command": "total", "release": "1.0", "lines": lines}),
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 85200},
        )

    def test_round_each_line_before_summing(self):
        self.check_total([line("1", "A", "S", 19),
                          line("2", "A", "S", 19)], 4, 34)

    def test_all_dates_and_input_order(self):
        lines = [line("z", "A", "S", 19999, "2099-12-31"),
                 line("a", "A", "S", 7, "2020-01-01"),
                 line("é", "A", "S", 7)]
        self.check_total(lines, 3000, 17013)
        self.check_total(list(reversed(lines)), 3000, 17013)

    def test_integer_precision_for_large_charge(self):
        charge = 10**100 + 19
        self.check_total([line("L", "A", "S", charge)], 3000, charge - 3000)


if __name__ == "__main__":
    unittest.main()
