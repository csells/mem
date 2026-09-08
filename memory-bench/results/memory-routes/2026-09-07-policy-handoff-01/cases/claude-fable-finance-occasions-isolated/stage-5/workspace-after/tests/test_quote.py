import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def line(line_id, account="A", subscription="S", service_on="2026-04-15", charge=1000):
    return {"line_id": line_id, "account_id": account, "subscription_id": subscription,
            "service_on": service_on, "charge_cents": charge}


class QuoteCliTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def test_explicit_release(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-1", charge=19999)})
        self.assertEqual(got, {"release": "1.0", "line_id": "L-1",
                               "credit_cents": 1999, "amount_due_cents": 18000})

    def test_omitted_release_selects_current(self):
        got = self.run_cli({"command": "quote", "line": line("L-2", charge=19999)})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-2",
                               "credit_cents": 2999, "amount_due_cents": 17000})

    def test_single_line_is_capped(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-3", charge=100000)})
        self.assertEqual(got["credit_cents"], 2400)
        self.assertEqual(got["amount_due_cents"], 97600)

    def test_zero_charge(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-4", charge=0)})
        self.assertEqual(got["credit_cents"], 0)
        self.assertEqual(got["amount_due_cents"], 0)

    def test_rounds_down_per_line(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-5", charge=9)})
        self.assertEqual(got["credit_cents"], 0)
        self.assertEqual(got["amount_due_cents"], 9)

    def test_unsupported_release(self):
        got = self.run_cli({"command": "quote", "release": "9.9", "line": line("L-6")})
        self.assertEqual(got, {"error": "unsupported_release"})


class CreditEngineTests(unittest.TestCase):
    def test_cap_shared_across_subscriptions_of_one_account(self):
        lines = [line("L-1", subscription="S1", charge=20000),
                 line("L-2", subscription="S2", service_on="2026-04-16", charge=20000)]
        self.assertEqual(main.assign_credits(lines, "1.0"), {"L-1": 2000, "L-2": 400})

    def test_distinct_accounts_have_independent_caps(self):
        lines = [line("L-1", account="A", charge=30000), line("L-2", account="B", charge=30000)]
        self.assertEqual(main.assign_credits(lines, "1.0"), {"L-1": 2400, "L-2": 2400})

    def test_earliest_service_date_first_then_line_id(self):
        lines = [line("L-b", service_on="2026-04-10", charge=15000),
                 line("L-a", service_on="2026-04-10", charge=15000),
                 line("L-0", service_on="2026-04-01", charge=5000)]
        self.assertEqual(main.assign_credits(lines, "1.0"), {"L-0": 500, "L-a": 1500, "L-b": 400})

    def test_code_point_order_for_line_ids(self):
        lines = [line("a", charge=20000), line("B", charge=20000)]
        self.assertEqual(main.assign_credits(lines, "1.0"), {"B": 2000, "a": 400})

    def test_empty_statement(self):
        self.assertEqual(main.assign_credits([], "1.0"), {})


if __name__ == "__main__":
    unittest.main()
