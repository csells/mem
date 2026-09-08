import unittest

from main import handle


def line(line_id, account, subscription, charge, service_on="2026-04-15"):
    return {
        "line_id": line_id,
        "account_id": account,
        "subscription_id": subscription,
        "service_on": service_on,
        "charge_cents": charge,
    }


class TotalTests(unittest.TestCase):
    def check_total(self, lines, credit, due):
        for release in ({}, {"release": "1.0"}):
            with self.subTest(release=release):
                self.assertEqual(
                    handle({"command": "total", "lines": lines, **release}),
                    {"release": "1.0", "credit_cents": credit,
                     "amount_due_cents": due},
                )

    def test_empty_and_zero(self):
        self.check_total([], 0, 0)
        self.check_total([line("zero", "A", "S", 0)], 0, 0)

    def test_shared_cap_across_subscriptions_and_lines(self):
        lines = [line("1", "A", "S1", 10000),
                 line("2", "A", "S1", 10000),
                 line("3", "A", "S2", 10000)]
        self.check_total(lines, 2400, 27600)

    def test_accounts_have_independent_caps_with_same_subscription_id(self):
        self.check_total([line("1", "A", "S", 30000),
                          line("2", "B", "S", 30000)], 4800, 55200)

    def test_round_each_line_before_summing(self):
        self.check_total([line("1", "A", "S", 19),
                          line("2", "A", "S", 19)], 2, 36)

    def test_all_dates_included_and_input_order_does_not_change_total(self):
        lines = [line("z", "A", "S", 20000, "2099-12-31"),
                 line("a", "A", "S", 10000, "2020-01-01")]
        self.check_total(lines, 2400, 27600)
        self.check_total(list(reversed(lines)), 2400, 27600)

    def test_single_line_matches_quote(self):
        charge = line("1", "A", "S", 30000)
        quote = handle({"command": "quote", "line": charge})
        self.assertEqual(quote.pop("line_id"), "1")
        self.assertEqual(handle({"command": "total", "lines": [charge]}), quote)


if __name__ == "__main__":
    unittest.main()
