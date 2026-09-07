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

    def test_export_empty(self):
        self.assertEqual(self.call({"command": "export", "accounts": []}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n",
            "count": 0,
        })

    def test_export_csv_fields(self):
        cases = [
            ("plain", "plain"),
            ("member-日", "member-日"),
            (" space\t", " space\t"),
            ("a,b", '"a,b"'),
            ('a"b', '"a""b"'),
            ("a\rb", '"a\rb"'),
            ("a\nb", '"a\nb"'),
            ('a,"\r\nb', '"a,""\r\nb"'),
        ]
        for customer_id, encoded_id in cases:
            with self.subTest(customer_id=customer_id):
                account = {
                    "customer_id": customer_id,
                    "renewal_on": "2026-04-15",
                    "plan_cents": 19999,
                    "completed_years": 2,
                    "autopay": True,
                }
                self.assertEqual(self.call({"command": "export", "accounts": [account]}), {
                    "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                           + encoded_id + ",2026-03-25,1999,18000\n",
                    "count": 1,
                })

    def test_export_order_duplicates_and_notice_values(self):
        accounts = [
            {"customer_id": "z", "renewal_on": "2020-01-01", "plan_cents": 0,
             "completed_years": 2, "autopay": True},
            {"customer_id": "a", "renewal_on": "2024-03-21", "plan_cents": 90000,
             "completed_years": 8, "autopay": True},
            {"customer_id": "z", "renewal_on": "2099-12-31", "plan_cents": 10**30,
             "completed_years": 1, "autopay": True},
            {"customer_id": "z", "renewal_on": "2024-02-29", "plan_cents": 19999,
             "completed_years": 2, "autopay": False},
        ]
        self.assertEqual(self.call({"command": "export", "accounts": accounts}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                   "z,2019-12-11,0,0\n"
                   "a,2024-02-29,2400,87600\n"
                   "z,2099-12-10,0,1000000000000000000000000000000\n"
                   "z,2024-02-08,0,19999\n",
            "count": 4,
        })

    def test_notice_credit(self):
        cases = [
            (19999, 2, True, 1999),
            (19999, 2, False, 0),
            (19999, 1, True, 0),
            (19999, 0, False, 0),
            (90000, 8, True, 2400),
            (23999, 2, True, 2399),
            (24000, 2, True, 2400),
            (24010, 2, True, 2400),
            (0, 2, True, 0),
            (9, 2, True, 0),
            (10, 2, True, 1),
            (10**30, 2, True, 2400),
        ]
        for plan_cents, years, autopay, credit in cases:
            with self.subTest(plan_cents=plan_cents, years=years, autopay=autopay):
                account = {
                    "customer_id": "M-17",
                    "renewal_on": "2026-04-15",
                    "plan_cents": plan_cents,
                    "completed_years": years,
                    "autopay": autopay,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "M-17",
                    "send_on": "2026-03-25",
                    "credit_cents": credit,
                    "amount_due_cents": plan_cents - credit,
                })

    def test_notice_calendar_boundaries(self):
        for renewal_on, send_on in [
            ("2020-01-01", "2019-12-11"),
            ("2024-03-21", "2024-02-29"),
            ("2024-02-29", "2024-02-08"),
            ("2025-03-01", "2025-02-08"),
            ("2099-12-31", "2099-12-10"),
        ]:
            with self.subTest(renewal_on=renewal_on):
                account = {
                    "customer_id": "member-日",
                    "renewal_on": renewal_on,
                    "plan_cents": 100,
                    "completed_years": 2,
                    "autopay": True,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "member-日",
                    "send_on": send_on,
                    "credit_cents": 10,
                    "amount_due_cents": 90,
                })


if __name__ == "__main__":
    unittest.main()
