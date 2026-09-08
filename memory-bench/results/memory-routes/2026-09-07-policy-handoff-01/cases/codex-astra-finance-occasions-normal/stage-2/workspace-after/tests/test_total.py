import unittest

from main import handle


def line(line_id, account_id, subscription_id, charge_cents,
         service_on="2026-04-15"):
    return {
        "line_id": line_id,
        "account_id": account_id,
        "subscription_id": subscription_id,
        "service_on": service_on,
        "charge_cents": charge_cents,
    }


class TotalTests(unittest.TestCase):
    def check_total(self, lines, credit, due):
        for release in (None, "1.0"):
            with self.subTest(release=release):
                request = {"command": "total", "lines": lines}
                if release is not None:
                    request["release"] = release
                self.assertEqual(handle(request), {
                    "release": "1.0",
                    "credit_cents": credit,
                    "amount_due_cents": due,
                })

    def test_empty_and_single_line(self):
        self.check_total([], 0, 0)
        self.check_total([line("L-1", "A", "S", 19999)], 1999, 18000)

    def test_account_cap_shared_across_subscriptions_and_lines(self):
        lines = [
            line("L-1", "A", "S-1", 10000),
            line("L-2", "A", "S-1", 10000),
            line("L-3", "A", "S-2", 10000),
        ]
        self.check_total(lines, 2400, 27600)
        self.check_total(list(reversed(lines)), 2400, 27600)
        # Each request starts a fresh statement cap.
        self.check_total([lines[0]], 1000, 9000)

    def test_accounts_have_independent_caps_with_same_subscription_id(self):
        self.check_total([
            line("L-1", "A", "S", 30000),
            line("L-2", "B", "S", 40000),
            line("L-3", "C", "S", 1000),
        ], 4900, 66100)

    def test_rounding_is_per_line_and_dates_do_not_exclude_lines(self):
        self.check_total([
            line("L-1", "A", "S", 19, "2020-01-01"),
            line("L-2", "A", "S", 19, "2099-12-31"),
            line("L-3", "B", "S", 9),
            line("L-4", "B", "S", 0),
        ], 2, 45)

    def test_cap_boundary_and_large_integer_charges(self):
        for charge, credit in ((13999, 2399), (14000, 2400),
                               (14010, 2400), (10**20, 2400)):
            with self.subTest(charge=charge):
                self.check_total([
                    line("L-1", "A", "S-1", 10000),
                    line("L-2", "A", "S-2", charge),
                ], credit, 10000 + charge - credit)
