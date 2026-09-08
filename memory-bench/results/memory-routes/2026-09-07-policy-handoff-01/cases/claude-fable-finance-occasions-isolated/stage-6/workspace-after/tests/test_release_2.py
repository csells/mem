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


class Release2CliTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def test_omitted_release_quote_uses_2_0(self):
        got = self.run_cli({"command": "quote", "line": line("L-1", charge=19999)})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-1",
                               "credit_cents": 2999, "amount_due_cents": 17000})

    def test_explicit_release_2_0_quote(self):
        got = self.run_cli({"command": "quote", "release": "2.0", "line": line("L-1", charge=19999)})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-1",
                               "credit_cents": 2999, "amount_due_cents": 17000})

    def test_explicit_release_1_0_still_uses_original_agreement(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-1", charge=19999)})
        self.assertEqual(got, {"release": "1.0", "line_id": "L-1",
                               "credit_cents": 1999, "amount_due_cents": 18000})

    def test_single_line_capped_at_3000(self):
        got = self.run_cli({"command": "quote", "line": line("L-1", charge=100000)})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-1",
                               "credit_cents": 3000, "amount_due_cents": 97000})

    def test_rounds_down_per_line(self):
        # 15% of 9 is 1.35 -> 1; 15% of 6 is 0.9 -> 0.
        got = self.run_cli({"command": "quote", "line": line("L-1", charge=9)})
        self.assertEqual(got["credit_cents"], 1)
        self.assertEqual(got["amount_due_cents"], 8)
        got = self.run_cli({"command": "quote", "line": line("L-2", charge=6)})
        self.assertEqual(got["credit_cents"], 0)
        self.assertEqual(got["amount_due_cents"], 6)

    def test_omitted_release_total_uses_2_0(self):
        got = self.run_cli({"command": "total", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000})

    def test_empty_total(self):
        got = self.run_cli({"command": "total", "release": "2.0", "lines": []})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_cap_is_per_subscription_not_per_account(self):
        # Under 1.0 the account cap would give 2400 total; under 2.0 each subscription caps at 3000.
        lines = [line("L-1", subscription="S1", charge=30000),
                 line("L-2", subscription="S2", charge=30000)]
        got = self.run_cli({"command": "total", "lines": lines})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000})

    def test_cap_is_shared_within_one_subscription(self):
        lines = [line("L-1", charge=15000), line("L-2", charge=15000)]
        got = self.run_cli({"command": "total", "lines": lines})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 27000})

    def test_same_subscription_id_under_different_accounts_is_not_one_group(self):
        lines = [line("L-1", account="A", subscription="S", charge=30000),
                 line("L-2", account="B", subscription="S", charge=30000)]
        got = self.run_cli({"command": "total", "lines": lines})
        self.assertEqual(got["credit_cents"], 6000)

    def test_total_ignores_service_dates(self):
        lines = [line("L-1", service_on="2020-01-01", charge=10000),
                 line("L-2", service_on="2099-12-31", charge=10000)]
        got = self.run_cli({"command": "total", "lines": lines})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 17000})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "total", "release": "3.0", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})


class Release2EngineTests(unittest.TestCase):
    def test_largest_charge_first_then_line_id(self):
        # 15% of 12000 = 1800; 15% of 8000 = 1200 fits the remaining 1200; the last line gets 0.
        lines = [line("L-c", service_on="2026-04-01", charge=8000),
                 line("L-b", service_on="2026-04-10", charge=8000),
                 line("L-a", service_on="2026-04-20", charge=12000)]
        self.assertEqual(main.assign_credits(lines), {"L-a": 1800, "L-b": 1200, "L-c": 0})

    def test_partial_remainder_goes_to_next_line(self):
        lines = [line("L-1", charge=15000), line("L-2", charge=10000), line("L-3", charge=10000)]
        # 2250 first, then 1500 uncapped but only 750 remaining, then 0.
        self.assertEqual(main.assign_credits(lines), {"L-1": 2250, "L-2": 750, "L-3": 0})

    def test_code_point_order_for_line_ids(self):
        lines = [line("a", charge=20000), line("B", charge=20000)]
        self.assertEqual(main.assign_credits(lines, "2.0"), {"B": 3000, "a": 0})

    def test_default_release_is_current(self):
        self.assertEqual(main.CURRENT_RELEASE, "2.0")
        lines = [line("L-1", charge=19999)]
        self.assertEqual(main.assign_credits(lines), main.assign_credits(lines, "2.0"))

    def test_release_1_engine_unchanged(self):
        lines = [line("L-1", subscription="S1", charge=20000),
                 line("L-2", subscription="S2", service_on="2026-04-16", charge=20000)]
        self.assertEqual(main.assign_credits(lines, "1.0"), {"L-1": 2000, "L-2": 400})

    def test_empty_statement(self):
        self.assertEqual(main.assign_credits([]), {})


if __name__ == "__main__":
    unittest.main()
