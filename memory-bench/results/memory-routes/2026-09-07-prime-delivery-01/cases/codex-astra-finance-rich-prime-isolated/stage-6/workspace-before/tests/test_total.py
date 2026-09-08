import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def line(line_id, charge_cents, account_id="A", subscription_id="S",
         service_on="2026-04-15"):
    return dict(line_id=line_id, charge_cents=charge_cents,
                account_id=account_id, subscription_id=subscription_id,
                service_on=service_on)


class TotalTests(unittest.TestCase):
    def check_total(self, lines, credit_cents, amount_due_cents):
        for release in (None, "1.0"):
            with self.subTest(release=release):
                request = {"command": "total", "lines": lines}
                if release is not None:
                    request["release"] = release
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps(request), text=True, capture_output=True,
                    check=True,
                )
                self.assertEqual(json.loads(result.stdout), {
                    "release": "1.0", "credit_cents": credit_cents,
                    "amount_due_cents": amount_due_cents,
                })

    def test_empty_and_zero_statements(self):
        self.check_total([], 0, 0)
        self.check_total([line("zero", 0)], 0, 0)

    def test_account_cap_spans_subscriptions_and_repeated_lines(self):
        self.check_total([
            line("1", 10000), line("2", 10000),
            line("3", 10000, subscription_id="T"),
        ], 2400, 27600)

    def test_same_subscription_id_in_separate_accounts_has_separate_caps(self):
        self.check_total([
            line("1", 30000), line("2", 30000, account_id="B"),
        ], 4800, 55200)

    def test_rounding_happens_per_line(self):
        self.check_total([line("1", 19), line("2", 19)], 2, 36)

    def test_cap_boundary(self):
        for charge, credit, due in ((23999, 2399, 21600),
                                    (24000, 2400, 21600),
                                    (24010, 2400, 21610)):
            with self.subTest(charge=charge):
                self.check_total([line("1", charge)], credit, due)

    def test_all_dates_included_and_input_order_does_not_change_total(self):
        lines = [line("Ω", 19999, service_on="2099-12-31"),
                 line("a", 19999, service_on="2020-01-01")]
        self.check_total(lines, 2400, 37598)
        self.check_total(list(reversed(lines)), 2400, 37598)

    def test_large_integer_charge(self):
        self.check_total([line("1", 10**30 + 9)], 2400, 10**30 - 2391)
