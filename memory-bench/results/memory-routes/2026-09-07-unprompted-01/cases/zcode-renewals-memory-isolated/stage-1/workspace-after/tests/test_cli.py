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

    def test_notice_credit_is_capped(self):
        self.assertEqual(
            self.notice(plan_cents=90000, completed_years=8),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 2400, "amount_due_cents": 87600},
        )

    def test_notice_send_date_crosses_leap_day(self):
        self.assertEqual(
            self.notice(renewal_on="2024-03-21")["send_on"],
            "2024-02-29",
        )

    def test_notice_send_date_crosses_leap_day_in_non_leap_year(self):
        self.assertEqual(
            self.notice(renewal_on="2023-03-21")["send_on"],
            "2023-02-28",
        )

    def test_notice_send_date_crosses_year_boundary(self):
        self.assertEqual(
            self.notice(renewal_on="2027-01-10")["send_on"],
            "2026-12-20",
        )


if __name__ == "__main__":
    unittest.main()
