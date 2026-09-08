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

    def test_empty_statement(self):
        got = self.check_total([], release="1.0")
        self.assertEqual(got, {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_omitted_release_selects_current(self):
        got = self.check_total([])
        self.assertEqual(got, {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_single_line_matches_quote_example(self):
        got = self.check_total([line("L-1", "A", "S", "2026-04-15", 19999)])
        self.assertEqual(got, {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000})

    def test_cap_shared_across_subscriptions_of_one_account(self):
        lines = [
            line("L-1", "A", "S1", "2026-04-01", 20000),
            line("L-2", "A", "S2", "2026-04-20", 20000),
        ]
        got = self.check_total(lines)
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600})

    def test_priority_earlier_service_date_then_line_id(self):
        lines = [
            line("L-b2", "B", "S", "2026-05-05", 30000),
            line("L-b1", "B", "S", "2026-05-05", 30000),
            line("L-b0", "B", "S", "2026-04-01", 1000),
        ]
        # L-b0 (earliest) 100; L-b1 then L-b2 tie on date, split by line_id:
        # L-b1 takes min(3000, 2300)=2300, L-b2 gets 0.
        got = self.check_total(lines)
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 58600})

    def test_distinct_accounts_have_independent_caps(self):
        lines = [
            line("L-1", "A", "S", "2026-04-15", 30000),
            line("L-2", "Z", "S", "2026-04-15", 30000),
        ]
        got = self.check_total(lines)
        self.assertEqual(got, {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200})

    def test_rounding_is_per_line_before_summing(self):
        lines = [
            line("L-1", "A1", "S", "2026-04-15", 1999),
            line("L-2", "A2", "S", "2026-04-15", 1999),
            line("L-3", "A3", "S", "2026-04-15", 1999),
        ]
        got = self.check_total(lines)
        self.assertEqual(got, {"release": "1.0", "credit_cents": 597, "amount_due_cents": 5400})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "total", "release": "0.9", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})
