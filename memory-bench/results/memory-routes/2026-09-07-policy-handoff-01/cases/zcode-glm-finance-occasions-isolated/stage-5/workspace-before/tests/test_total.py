import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account_id, subscription_id, service_on, charge_cents):
    return {
        "line_id": line_id,
        "account_id": account_id,
        "subscription_id": subscription_id,
        "service_on": service_on,
        "charge_cents": charge_cents,
    }


class TotalTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def check_total(self, lines, release=None):
        request = {"command": "total", "lines": lines}
        if release is not None:
            request["release"] = release
        return self.run_cli(request)

    def test_empty_statement_release_1_0(self):
        got = self.check_total([], release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_empty_statement_release_2_0(self):
        got = self.check_total([], release="2.0")
        self.assertEqual(got, {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_omitted_release_selects_current(self):
        got = self.check_total([])
        self.assertEqual(got, {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_single_line_matches_quote_example(self):
        got = self.check_total([line("L-1", "A", "S", "2026-04-15", 19999)])
        self.assertEqual(got, {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000})

    # Release 1.0 agreement, retained for explicit requests.

    def test_cap_shared_across_subscriptions_of_one_account(self):
        lines = [
            line("L-1", "A", "S1", "2026-04-01", 20000),
            line("L-2", "A", "S2", "2026-04-20", 20000),
        ]
        got = self.check_total(lines, release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600})

    def test_priority_earlier_service_date_then_line_id(self):
        lines = [
            line("L-b2", "B", "S", "2026-05-05", 30000),
            line("L-b1", "B", "S", "2026-05-05", 30000),
            line("L-b0", "B", "S", "2026-04-01", 1000),
        ]
        # L-b0 (earliest) 100; L-b1 then L-b2 tie on date, split by line_id:
        # L-b1 takes min(3000, 2300)=2300, L-b2 gets 0.
        got = self.check_total(lines, release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 58600})

    def test_distinct_accounts_have_independent_caps(self):
        lines = [
            line("L-1", "A", "S", "2026-04-15", 30000),
            line("L-2", "Z", "S", "2026-04-15", 30000),
        ]
        got = self.check_total(lines, release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200})

    def test_rounding_is_per_line_before_summing_release_1_0(self):
        lines = [
            line("L-1", "A1", "S", "2026-04-15", 1999),
            line("L-2", "A2", "S", "2026-04-15", 1999),
            line("L-3", "A3", "S", "2026-04-15", 1999),
        ]
        got = self.check_total(lines, release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 597, "amount_due_cents": 5400})

    # Release 2.0 agreement, current as of its adoption.

    def test_rounding_is_per_line_before_summing_release_2_0(self):
        lines = [
            line("L-1", "A1", "S", "2026-04-15", 1999),
            line("L-2", "A2", "S", "2026-04-15", 1999),
            line("L-3", "A3", "S", "2026-04-15", 1999),
        ]
        got = self.check_total(lines, release="2.0")
        self.assertEqual(got, {"release": "2.0", "credit_cents": 897, "amount_due_cents": 5100})

    def test_same_subscription_id_under_different_accounts_independent(self):
        lines = [
            line("L-1", "A", "S", "2026-04-15", 30000),
            line("L-2", "Z", "S", "2026-04-15", 30000),
        ]
        got = self.check_total(lines, release="2.0")
        self.assertEqual(got, {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000})

    def test_cap_group_and_priority_largest_charge_then_line_id(self):
        lines = [
            line("L-1", "A", "S", "2026-05-05", 25000),
            line("L-2", "A", "S", "2026-04-20", 25000),
            line("L-3", "A", "S", "2026-01-01", 10000),
            line("L-4", "A", "T", "2026-04-15", 25000),
            line("L-5", "B", "S", "2026-04-15", 20000),
        ]
        # (A,S): L-1 and L-2 tie at 25000, L-1 first by line_id, takes the
        # whole 3000 cap despite L-3's earlier service date; L-4 in (A,T) and
        # L-5 in (B,S) have independent caps.
        got = self.check_total(lines, release="2.0")
        self.assertEqual(got, {"release": "2.0", "credit_cents": 9000, "amount_due_cents": 96000})

    def test_later_line_receives_only_remaining_credit(self):
        lines = [
            line("L-1", "A", "S", "2026-04-01", 19400),
            line("L-2", "A", "S", "2026-04-02", 1000),
        ]
        # L-1 takes 2910, leaving 90 of the 3000 cap; L-2's uncapped 150
        # exceeds that, so it receives only the remaining 90.
        got = self.check_total(lines, release="2.0")
        self.assertEqual(got, {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 17400})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "total", "release": "0.9", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})
