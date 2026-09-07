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

    def test_notice_credit(self):
        cases = [
            (19999, 3, True, 2999),
            (19999, 3, False, 2999),
            (19999, 2, True, 0),
            (19999, 2, False, 0),
            (19999, 1, True, 0),
            (19999, 0, False, 0),
            (90000, 8, True, 3600),
            (90000, 8, False, 3600),
            (23999, 3, False, 3599),
            (24000, 3, True, 3600),
            (24010, 3, False, 3600),
            (0, 3, True, 0),
            (6, 3, False, 0),
            (7, 3, True, 1),
            (10**30 + 1, 3, False, 3600),
        ]
        for plan, years, autopay, credit in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay):
                account = {
                    "customer_id": "M-17", "renewal_on": "2026-04-15",
                    "plan_cents": plan, "completed_years": years, "autopay": autopay,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "M-17", "send_on": "2026-04-01",
                    "credit_cents": credit, "amount_due_cents": plan - credit,
                })

    def test_notice_calendar_dates(self):
        cases = [
            ("2020-01-01", "2019-12-18"),
            ("2024-02-29", "2024-02-15"),
            ("2024-03-14", "2024-02-29"),
            ("2025-03-14", "2025-02-28"),
            ("2099-12-31", "2099-12-17"),
        ]
        for renewal_on, send_on in cases:
            with self.subTest(renewal_on=renewal_on):
                account = {
                    "customer_id": "calendar-member", "renewal_on": renewal_on,
                    "plan_cents": 100, "completed_years": 0, "autopay": False,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "calendar-member", "send_on": send_on,
                    "credit_cents": 0, "amount_due_cents": 100,
                })

    def test_batch_filter_order_duplicates_and_total(self):
        accounts = [
            {"customer_id": "Z", "renewal_on": "2026-04-15",
             "plan_cents": 19999, "completed_years": 3, "autopay": False},
            {"customer_id": "excluded", "renewal_on": "2026-04-22",
             "plan_cents": 10000, "completed_years": 9, "autopay": True},
            {"customer_id": "A", "renewal_on": "2026-04-15",
             "plan_cents": 90000, "completed_years": 8, "autopay": True},
            {"customer_id": "Z", "renewal_on": "2026-04-15",
             "plan_cents": 500, "completed_years": 2, "autopay": True},
        ]
        accounts.append(accounts[0].copy())
        self.assertEqual(self.call({
            "command": "batch", "on": "2026-04-01", "accounts": accounts,
        }), {
            "on": "2026-04-01",
            "notices": [
                {"customer_id": "Z", "send_on": "2026-04-01",
                 "credit_cents": 2999, "amount_due_cents": 17000},
                {"customer_id": "A", "send_on": "2026-04-01",
                 "credit_cents": 3600, "amount_due_cents": 86400},
                {"customer_id": "Z", "send_on": "2026-04-01",
                 "credit_cents": 0, "amount_due_cents": 500},
                {"customer_id": "Z", "send_on": "2026-04-01",
                 "credit_cents": 2999, "amount_due_cents": 17000},
            ],
            "total_due_cents": 120900,
        })

    def test_batch_empty_results(self):
        account = {
            "customer_id": "M-17", "renewal_on": "2026-04-15",
            "plan_cents": 100, "completed_years": 0, "autopay": False,
        }
        for accounts in ([], [account]):
            with self.subTest(accounts=accounts):
                self.assertEqual(self.call({
                    "command": "batch", "on": "2026-04-02", "accounts": accounts,
                }), {"on": "2026-04-02", "notices": [], "total_due_cents": 0})

    def test_batch_calendar_dates_match_notice(self):
        for renewal_on, on in [
            ("2020-01-01", "2019-12-18"),
            ("2024-03-14", "2024-02-29"),
            ("2025-03-14", "2025-02-28"),
            ("2099-12-31", "2099-12-17"),
        ]:
            with self.subTest(renewal_on=renewal_on):
                account = {
                    "customer_id": 'M-é,"\n', "renewal_on": renewal_on,
                    "plan_cents": 0, "completed_years": 3, "autopay": False,
                }
                notice = self.call({"command": "notice", "account": account})
                self.assertEqual(self.call({
                    "command": "batch", "on": on, "accounts": [account],
                }), {"on": on, "notices": [notice], "total_due_cents": 0})

    def test_export_empty(self):
        self.assertEqual(self.call({"command": "export", "accounts": []}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n",
            "count": 0,
        })

    def test_export_csv_quoting(self):
        cases = [
            ("plain", "plain"),
            (" space \t", " space \t"),
            ("M-é", "M-é"),
            ("a,b", '"a,b"'),
            ('a"b', '"a""b"'),
            ("a\rb", '"a\rb"'),
            ("a\nb", '"a\nb"'),
            ('a,"\r\nb', '"a,""\r\nb"'),
        ]
        for customer_id, encoded_id in cases:
            with self.subTest(customer_id=customer_id):
                account = {
                    "customer_id": customer_id, "renewal_on": "2026-04-15",
                    "plan_cents": 19999, "completed_years": 3, "autopay": False,
                }
                self.assertEqual(self.call({"command": "export", "accounts": [account]}), {
                    "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                           + encoded_id + ",2026-04-01,2999,17000\n",
                    "count": 1,
                })

    def test_export_order_duplicates_and_notice_values(self):
        accounts = [
            {"customer_id": "Z", "renewal_on": "2020-01-01",
             "plan_cents": 90000, "completed_years": 8, "autopay": False},
            {"customer_id": "A", "renewal_on": "2024-03-21",
             "plan_cents": 0, "completed_years": 0, "autopay": False},
            {"customer_id": "Z", "renewal_on": "2025-03-21",
             "plan_cents": 19999, "completed_years": 2, "autopay": True},
        ]
        self.assertEqual(self.call({"command": "export", "accounts": accounts}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                   "Z,2019-12-18,3600,86400\n"
                   "A,2024-03-07,0,0\n"
                   "Z,2025-03-07,0,19999\n",
            "count": 3,
        })


if __name__ == "__main__":
    unittest.main()
