import unittest

from main import handle
from test_total import line


class Release2Tests(unittest.TestCase):
    def check_request(self, request, expected):
        for release in (None, "2.0"):
            with self.subTest(release=release):
                versioned = dict(request)
                if release is not None:
                    versioned["release"] = release
                self.assertEqual(handle(versioned), {"release": "2.0", **expected})

    def check_total(self, lines, credit):
        self.check_request({"command": "total", "lines": lines}, {
            "credit_cents": credit,
            "amount_due_cents": sum(item["charge_cents"] for item in lines) - credit,
        })

    def test_quote_rounding_cap_and_date_endpoints(self):
        for charge, credit in ((0, 0), (6, 0), (7, 1), (19, 2),
                               (19999, 2999), (20000, 3000),
                               (20007, 3000), (10**20, 3000)):
            for date in ("2020-01-01", "2099-12-31"):
                with self.subTest(charge=charge, date=date):
                    self.check_request({
                        "command": "quote",
                        "line": line("L-Ω", "A", "S", charge, date),
                    }, {"line_id": "L-Ω", "credit_cents": credit,
                        "amount_due_cents": charge - credit})

    def test_empty_and_single_line_total(self):
        self.check_total([], 0)
        self.check_total([line("L", "A", "S", 19999)], 2999)

    def test_cap_groups_use_both_account_and_subscription(self):
        lines = [line("1", "A", "S", 15000),
                 line("2", "A", "S", 10000),
                 line("3", "A", "T", 30000),
                 line("4", "B", "S", 30000)]
        self.check_total(lines, 9000)
        self.check_total(list(reversed(lines)), 9000)
        self.check_total([lines[0]], 2250)
        # Switching versions does not retain the preceding statement's caps.
        self.assertEqual(handle({"command": "total", "release": "1.0",
                                 "lines": lines}), {
            "release": "1.0", "credit_cents": 4800, "amount_due_cents": 80200,
        })
        self.check_total(lines, 9000)

    def test_round_each_line_before_summing_and_capping(self):
        self.check_total([line("1", "A", "S", 6, "2020-01-01"),
                          line("2", "A", "S", 6, "2099-12-31")], 0)
        for charge, credit in ((9999, 2999), (10000, 3000),
                               (10007, 3000), (10**20, 3000)):
            with self.subTest(charge=charge):
                self.check_total([line("1", "A", "S", 10000),
                                  line("2", "A", "S", charge)], credit)

    def test_group_ids_are_pairs_without_string_collisions(self):
        self.check_total([line("1", "A:B", "C", 30000),
                          line("2", "A", "B:C", 30000)], 6000)
