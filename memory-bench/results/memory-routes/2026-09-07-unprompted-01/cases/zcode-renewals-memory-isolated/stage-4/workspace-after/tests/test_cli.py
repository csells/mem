import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def call(self, request):
        result = subprocess.run([sys.executable, str(ROOT / "main.py")], input=json.dumps(request), capture_output=True, text=True, check=True, timeout=3)
        return json.loads(result.stdout)

    def test_ping(self):
        self.assertEqual(self.call({"command": "ping"}), {"status": "ok", "product": "HarborPass"})

    def test_unknown_command(self):
        self.assertEqual(self.call({"command": "not_a_command"}), {"error": "unknown_command"})

    def notice(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 3,
            "autopay": False,
        }
        account.update(overrides)
        return self.call({"command": "notice", "account": account})

    def test_notice_approved_example(self):
        self.assertEqual(
            self.notice(),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_notice_below_three_years_gets_no_credit(self):
        self.assertEqual(
            self.notice(completed_years=2, autopay=True),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 0, "amount_due_cents": 19999},
        )

    def test_notice_autopay_does_not_affect_eligibility(self):
        self.assertEqual(
            self.notice(autopay=True),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_notice_credit_is_capped(self):
        self.assertEqual(
            self.notice(plan_cents=90000, completed_years=8),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 3600, "amount_due_cents": 86400},
        )

    def replay(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 2,
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "support_replay", "case_id": "IOS-1842", "account": account})

    def test_support_replay_approved_example(self):
        self.assertEqual(
            self.replay(plan_cents=500),
            {"case_id": "IOS-1842", "notice": {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 50, "amount_due_cents": 450}},
        )

    def test_support_replay_rounds_credit_down(self):
        self.assertEqual(
            self.replay(),
            {"case_id": "IOS-1842", "notice": {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 1999, "amount_due_cents": 18000}},
        )

    def test_support_replay_without_autopay_gets_no_credit(self):
        self.assertEqual(
            self.replay(autopay=False),
            {"case_id": "IOS-1842", "notice": {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999}},
        )

    def test_support_replay_credit_is_capped(self):
        self.assertEqual(
            self.replay(plan_cents=90000, completed_years=8),
            {"case_id": "IOS-1842", "notice": {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 2400, "amount_due_cents": 87600}},
        )

    def test_notice_send_date_crosses_leap_day(self):
        self.assertEqual(
            self.notice(renewal_on="2024-03-14")["send_on"],
            "2024-02-29",
        )

    def test_notice_send_date_crosses_leap_day_in_non_leap_year(self):
        self.assertEqual(
            self.notice(renewal_on="2023-03-14")["send_on"],
            "2023-02-28",
        )

    def test_notice_send_date_crosses_year_boundary(self):
        self.assertEqual(
            self.notice(renewal_on="2027-01-10")["send_on"],
            "2026-12-27",
        )

    def export(self, accounts):
        return self.call({"command": "export", "accounts": accounts})

    def account(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 3,
            "autopay": False,
        }
        account.update(overrides)
        return account

    def test_export_approved_example(self):
        self.assertEqual(
            self.export([self.account()]),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\nM-17,2026-04-01,2999,17000\n", "count": 1},
        )

    def test_export_empty_collection(self):
        self.assertEqual(
            self.export([]),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\n", "count": 0},
        )

    def test_export_preserves_order_and_duplicates(self):
        csv = self.export([self.account(customer_id="B-2"), self.account(customer_id="A-1"), self.account(customer_id="B-2")])["csv"]
        rows = csv.rstrip("\n").split("\n")
        self.assertEqual(rows[1:], ["B-2,2026-04-01,2999,17000", "A-1,2026-04-01,2999,17000", "B-2,2026-04-01,2999,17000"])

    def test_export_rows_match_notice_values(self):
        csv = self.export([self.account(completed_years=2, autopay=True)])["csv"]
        self.assertEqual(csv, "customer_id,send_on,credit_cents,amount_due_cents\nM-17,2026-04-01,0,19999\n")

    def test_export_quotes_fields_with_commas(self):
        csv = self.export([self.account(customer_id="Doe, Jane")])["csv"]
        self.assertIn('"Doe, Jane",2026-04-01,2999,17000\n', csv)

    def test_export_quotes_fields_with_double_quotes(self):
        csv = self.export([self.account(customer_id='Say "hi"')])["csv"]
        self.assertIn('"Say ""hi""",2026-04-01,2999,17000\n', csv)

    def test_export_quotes_fields_with_line_breaks(self):
        csv = self.export([self.account(customer_id="two\nlines")])["csv"]
        self.assertIn('"two\nlines",2026-04-01,2999,17000\n', csv)

    def test_export_leaves_plain_fields_unquoted(self):
        csv = self.export([self.account(customer_id="A-1; B 2")])["csv"]
        self.assertIn("A-1; B 2,2026-04-01,2999,17000\n", csv)


if __name__ == "__main__":
    unittest.main()
