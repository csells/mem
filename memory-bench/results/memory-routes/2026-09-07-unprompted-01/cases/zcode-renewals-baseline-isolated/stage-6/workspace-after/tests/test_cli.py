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
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "notice", "account": account})

    def test_notice_revised_example(self):
        self.assertEqual(
            self.notice(),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_notice_credit_regardless_of_autopay(self):
        self.assertEqual(
            self.notice(autopay=False),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_notice_under_three_years_gets_no_credit(self):
        self.assertEqual(
            self.notice(completed_years=2),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 0, "amount_due_cents": 19999},
        )

    def test_notice_credit_capped_at_3600(self):
        self.assertEqual(
            self.notice(plan_cents=90000, completed_years=8),
            {"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 3600, "amount_due_cents": 86400},
        )

    def test_notice_send_date_crosses_leap_day(self):
        result = self.notice(renewal_on="2024-03-10")
        self.assertEqual(result["send_on"], "2024-02-25")

    def test_notice_send_date_crosses_year_boundary(self):
        result = self.notice(renewal_on="2021-01-10")
        self.assertEqual(result["send_on"], "2020-12-27")

    def account(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 3,
            "autopay": True,
        }
        account.update(overrides)
        return account

    def test_export_revised_example(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": [self.account()]}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\nM-17,2026-04-01,2999,17000\n", "count": 1},
        )

    def test_export_empty_collection_is_header_only(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": []}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\n", "count": 0},
        )

    def test_export_preserves_order_and_duplicate_ids(self):
        accounts = [self.account(customer_id="B-2"), self.account(customer_id="A-1", completed_years=2), self.account(customer_id="B-2")]
        result = self.call({"command": "export", "accounts": accounts})
        self.assertEqual(result["count"], 3)
        self.assertEqual(
            result["csv"],
            "customer_id,send_on,credit_cents,amount_due_cents\n"
            "B-2,2026-04-01,2999,17000\n"
            "A-1,2026-04-01,0,19999\n"
            "B-2,2026-04-01,2999,17000\n",
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
            '"Say ""ahoy"", mate",2026-04-01,2999,17000\n'
            '"line\nbreak",2026-04-01,2999,17000\n'
            '"carriage\rreturn",2026-04-01,2999,17000\n'
            "plain-id,2026-04-01,2999,17000\n",
        )

    def test_export_rows_match_notice_values(self):
        account = self.account(plan_cents=90000, completed_years=8)
        row = self.call({"command": "export", "accounts": [account]})["csv"].splitlines()[1]
        notice = self.call({"command": "notice", "account": account})
        self.assertEqual(row, "{customer_id},{send_on},{credit_cents},{amount_due_cents}".format(**notice))

    def batch(self, on, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 3,
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "batch", "on": on, "accounts": [account]})

    def batch_accounts(self, on, accounts):
        return self.call({"command": "batch", "on": on, "accounts": accounts})

    def test_batch_includes_only_accounts_sent_on_the_day(self):
        result = self.batch_accounts(
            "2026-04-01",
            [
                self.account(customer_id="M-17", renewal_on="2026-04-15"),
                self.account(customer_id="M-18", renewal_on="2026-04-16"),
            ],
        )
        self.assertEqual(
            result,
            {
                "on": "2026-04-01",
                "notices": [{"customer_id": "M-17", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000}],
                "total_due_cents": 17000,
            },
        )

    def test_batch_no_matches_returns_empty_notices_and_zero_total(self):
        self.assertEqual(
            self.batch_accounts("2026-04-01", [self.account(renewal_on="2026-04-16")]),
            {"on": "2026-04-01", "notices": [], "total_due_cents": 0},
        )

    def test_batch_empty_accounts_collection(self):
        self.assertEqual(
            self.batch_accounts("2026-04-01", []),
            {"on": "2026-04-01", "notices": [], "total_due_cents": 0},
        )

    def test_batch_preserves_order_and_duplicate_ids(self):
        result = self.batch_accounts(
            "2026-04-01",
            [
                self.account(customer_id="B-2", renewal_on="2026-04-16"),
                self.account(customer_id="A-1"),
                self.account(customer_id="B-2", completed_years=2),
            ],
        )
        self.assertEqual(
            result,
            {
                "on": "2026-04-01",
                "notices": [
                    {"customer_id": "A-1", "send_on": "2026-04-01", "credit_cents": 2999, "amount_due_cents": 17000},
                    {"customer_id": "B-2", "send_on": "2026-04-01", "credit_cents": 0, "amount_due_cents": 19999},
                ],
                "total_due_cents": 36999,
            },
        )

    def test_batch_match_uses_current_notice_send_date(self):
        self.assertEqual(
            self.batch("2026-04-01", renewal_on="2026-04-15")["notices"][0],
            self.notice(),
        )
        self.assertEqual(
            self.batch("2026-04-02", renewal_on="2026-04-15")["notices"],
            [],
        )

    def test_batch_send_date_crosses_leap_day_and_year_boundary(self):
        leap = self.batch_accounts("2024-02-25", [self.account(renewal_on="2024-03-10")])
        self.assertEqual([n["send_on"] for n in leap["notices"]], ["2024-02-25"])
        year_end = self.batch_accounts("2020-12-27", [self.account(renewal_on="2021-01-10")])
        self.assertEqual([n["send_on"] for n in year_end["notices"]], ["2020-12-27"])

    def test_batch_sums_amount_due_across_notices(self):
        result = self.batch_accounts(
            "2026-04-01",
            [
                self.account(plan_cents=90000, completed_years=8),
                self.account(completed_years=2),
            ],
        )
        self.assertEqual(result["total_due_cents"], 86400 + 19999)

    def test_batch_response_has_exact_keys(self):
        result = self.batch("2026-04-01")
        self.assertEqual(set(result), {"on", "notices", "total_due_cents"})
        self.assertEqual(set(result["notices"][0]), {"customer_id", "send_on", "credit_cents", "amount_due_cents"})

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

    def compat_notice(self, **overrides):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 2,
            "autopay": True,
        }
        account.update(overrides)
        return self.call({"command": "compat_notice", "release": "1.0", "account": account})

    def assert_compat_notice(self, notice, **overrides):
        self.assertEqual(
            self.compat_notice(**overrides),
            {"release": "1.0", "notice": notice},
        )

    def test_compat_notice_approved_release_1_0_example(self):
        self.assert_compat_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_compat_notice_zero_plan_and_tenure(self):
        self.assert_compat_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 0},
            plan_cents=0,
            completed_years=0,
        )

    def test_compat_notice_without_autopay_gets_no_credit(self):
        self.assert_compat_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
            autopay=False,
        )

    def test_compat_notice_under_two_years_gets_no_credit(self):
        self.assert_compat_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
            completed_years=1,
        )

    def test_compat_notice_credit_capped_at_2400(self):
        self.assert_compat_notice(
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 2400, "amount_due_cents": 87600},
            plan_cents=90000,
            completed_years=8,
        )

    def test_compat_notice_send_date_crosses_leap_day(self):
        result = self.compat_notice(renewal_on="2024-03-10")
        self.assertEqual(result["notice"]["send_on"], "2024-02-18")

    def test_compat_notice_send_date_crosses_year_boundary(self):
        result = self.compat_notice(renewal_on="2021-01-10")
        self.assertEqual(result["notice"]["send_on"], "2020-12-20")

    def test_compat_notice_uses_release_1_0_rules_not_current_policy(self):
        account = {
            "customer_id": "M-17",
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 3,
            "autopay": False,
        }
        current = self.call({"command": "notice", "account": account})
        self.assertEqual(current["credit_cents"], 2999)
        receipt = self.call({"command": "compat_notice", "release": "1.0", "account": account})
        self.assertEqual(receipt["notice"]["credit_cents"], 0)

    def test_compat_notice_response_has_exact_keys(self):
        result = self.compat_notice()
        self.assertEqual(set(result), {"release", "notice"})
        self.assertEqual(set(result["notice"]), {"customer_id", "send_on", "credit_cents", "amount_due_cents"})


if __name__ == "__main__":
    unittest.main()
