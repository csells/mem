import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account="A", subscription="S", service_on="2026-04-15", charge=1000):
    return {"line_id": line_id, "account_id": account, "subscription_id": subscription,
            "service_on": service_on, "charge_cents": charge}


class TotalCliTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def test_empty_statement(self):
        got = self.run_cli({"command": "total", "release": "1.0", "lines": []})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0})

    def test_single_line_matches_quote_example(self):
        got = self.run_cli({"command": "total", "release": "1.0", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000})

    def test_omitted_release_selects_current(self):
        got = self.run_cli({"command": "total", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000})

    def test_cap_is_shared_across_an_accounts_subscriptions(self):
        # Independent single-line quotes would credit 2000 + 2000; the statement caps at 2400.
        lines = [line("L-1", subscription="S1", charge=20000),
                 line("L-2", subscription="S2", service_on="2026-04-16", charge=20000)]
        got = self.run_cli({"command": "total", "release": "1.0", "lines": lines})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600})

    def test_distinct_accounts_have_independent_caps(self):
        lines = [line("L-1", account="A", charge=30000), line("L-2", account="B", charge=30000)]
        got = self.run_cli({"command": "total", "release": "1.0", "lines": lines})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200})

    def test_same_subscription_id_under_different_accounts_is_not_one_group(self):
        lines = [line("L-1", account="A", subscription="S", charge=30000),
                 line("L-2", account="B", subscription="S", charge=30000)]
        got = self.run_cli({"command": "total", "release": "1.0", "lines": lines})
        self.assertEqual(got["credit_cents"], 4800)

    def test_rounds_down_per_line_before_summing(self):
        # 10% of 9 is 0 per line, not floor(0.9 * 3).
        lines = [line("L-1", charge=9), line("L-2", charge=9), line("L-3", charge=9)]
        got = self.run_cli({"command": "total", "release": "1.0", "lines": lines})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 0, "amount_due_cents": 27})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "total", "release": "9.9", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})

    def test_quote_remains_available(self):
        got = self.run_cli({"command": "quote", "release": "1.0", "line": line("L-1", charge=19999)})
        self.assertEqual(got, {"release": "1.0", "line_id": "L-1",
                               "credit_cents": 1999, "amount_due_cents": 18000})


if __name__ == "__main__":
    unittest.main()
