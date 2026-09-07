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
            "completed_years": 2,
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "notice", "account": account})

    def test_notice_approved_example(self):
        self.assertEqual(
            self.notice(),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_notice_without_autopay_gets_no_credit(self):
        self.assertEqual(
            self.notice(autopay=False),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
        )

    def test_notice_under_two_years_gets_no_credit(self):
        self.assertEqual(
            self.notice(completed_years=1),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
        )

    def test_notice_credit_capped_at_2400(self):
        self.assertEqual(
            self.notice(plan_cents=90000, completed_years=8),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 2400, "amount_due_cents": 87600},
        )

    def test_notice_send_date_crosses_leap_day(self):
        result = self.notice(renewal_on="2024-03-10")
        self.assertEqual(result["send_on"], "2024-02-18")

    def test_notice_send_date_crosses_year_boundary(self):
        result = self.notice(renewal_on="2021-01-10")
        self.assertEqual(result["send_on"], "2020-12-20")

    def account(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 2,
            "autopay": True,
        }
        account.update(overrides)
        return account

    def test_export_approved_example(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": [self.account()]}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\nM-17,2026-03-25,1999,18000\n", "count": 1},
        )

    def test_export_empty_collection_is_header_only(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": []}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\n", "count": 0},
        )

    def test_export_preserves_order_and_duplicate_ids(self):
        accounts = [self.account(customer_id="B-2"), self.account(customer_id="A-1", autopay=False), self.account(customer_id="B-2")]
        result = self.call({"command": "export", "accounts": accounts})
        self.assertEqual(result["count"], 3)
        self.assertEqual(
            result["csv"],
            "customer_id,send_on,credit_cents,amount_due_cents\n"
            "B-2,2026-03-25,1999,18000\n"
            "A-1,2026-03-25,0,19999\n"
            "B-2,2026-03-25,1999,18000\n",
        )

    def test_export_quotes_only_special_fields(self):
        accounts = [
            self.account(customer_id='Say "ahoy", mate'),
            self.account(customer_id="line\nbreak"),
            self.account(customer_id="carriage\rreturn"),
            self.account(customer_id="plain-id"),
        ]
        result = self.call({"command": "export", "accounts": accounts})
        self.assertEqual(
            result["csv"],
            "customer_id,send_on,credit_cents,amount_due_cents\n"
            '"Say ""ahoy"", mate",2026-03-25,1999,18000\n'
            '"line\nbreak",2026-03-25,1999,18000\n'
            '"carriage\rreturn",2026-03-25,1999,18000\n'
            "plain-id,2026-03-25,1999,18000\n",
        )

    def test_export_rows_match_notice_values(self):
        account = self.account(plan_cents=90000, completed_years=8)
        row = self.call({"command": "export", "accounts": [account]})["csv"].splitlines()[1]
        notice = self.call({"command": "notice", "account": account})
        self.assertEqual(row, "{customer_id},{send_on},{credit_cents},{amount_due_cents}".format(**notice))

    def support_replay(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 2,
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "support_replay", "case_id": "IOS-1842", "account": account})

    def assert_replay_notice(self, notice, **overrides):
        self.assertEqual(
            self.support_replay(**overrides),
            {"case_id": "IOS-1842", "notice": notice},
        )

    def test_support_replay_approved_small_plan_example(self):
        self.assert_replay_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 50, "amount_due_cents": 450},
            plan_cents=500,
        )

    def test_support_replay_large_plan(self):
        self.assert_replay_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_support_replay_without_autopay_gets_no_credit(self):
        self.assert_replay_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
            autopay=False,
        )

    def test_support_replay_under_two_years_gets_no_credit(self):
        self.assert_replay_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
            completed_years=1,
        )

    def test_support_replay_credit_capped_at_2400(self):
        self.assert_replay_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 2400, "amount_due_cents": 87600},
            plan_cents=90000,
            completed_years=8,
        )

    def test_support_replay_send_date_crosses_leap_day(self):
        result = self.support_replay(renewal_on="2024-03-10")
        self.assertEqual(result["notice"]["send_on"], "2024-02-18")

    def test_support_replay_send_date_crosses_year_boundary(self):
        result = self.support_replay(renewal_on="2021-01-10")
        self.assertEqual(result["notice"]["send_on"], "2020-12-20")

    def test_support_replay_response_has_exact_keys(self):
        result = self.support_replay()
        self.assertEqual(set(result), {"case_id", "notice"})
        self.assertEqual(set(result["notice"]), {"customer_id", "send_on", "credit_cents", "amount_due_cents"})


if __name__ == "__main__":
    unittest.main()
