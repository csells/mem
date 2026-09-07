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
                           + encoded_id + ",2026-04-01,0,19999\n",
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
             "completed_years": 3, "autopay": False},
        ]
        self.assertEqual(self.call({"command": "export", "accounts": accounts}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                   "z,2019-12-18,0,0\n"
                   "a,2024-03-07,3600,86400\n"
                   "z,2099-12-17,0,1000000000000000000000000000000\n"
                   "z,2024-02-15,2999,17000\n",
            "count": 4,
        })

    def test_support_replay_release_1_0(self):
        cases = [
            (500, 2, True, "2026-04-15", "2026-03-25", 50),
            (19999, 2, True, "2026-04-15", "2026-03-25", 1999),
            (19999, 2, False, "2026-04-15", "2026-03-25", 0),
            (19999, 1, True, "2026-04-15", "2026-03-25", 0),
            (90000, 8, True, "2024-03-21", "2024-02-29", 2400),
            (23999, 2, True, "2024-02-29", "2024-02-08", 2399),
            (24000, 2, True, "2025-03-01", "2025-02-08", 2400),
            (0, 2, True, "2020-01-01", "2019-12-11", 0),
            (9, 2, True, "2099-12-31", "2099-12-10", 0),
            (10**30, 2, True, "2026-04-15", "2026-03-25", 2400),
        ]
        for price, years, autopay, renewal_on, send_on, credit in cases:
            with self.subTest(price=price, years=years, autopay=autopay):
                account = {
                    "customer_id": 'member-日,"\r\n',
                    "renewal_on": renewal_on,
                    "plan_cents": price,
                    "completed_years": years,
                    "autopay": autopay,
                }
                self.assertEqual(self.call({
                    "command": "support_replay", "case_id": "IOS-1842",
                    "account": account,
                }), {
                    "case_id": "IOS-1842",
                    "notice": {
                        "customer_id": 'member-日,"\r\n',
                        "send_on": send_on,
                        "credit_cents": credit,
                        "amount_due_cents": price - credit,
                    },
                })

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
            (23999, 3, True, 3599),
            (24000, 3, True, 3600),
            (24010, 3, True, 3600),
            (0, 3, True, 0),
            (6, 3, False, 0),
            (7, 3, False, 1),
            (10**30, 3, True, 3600),
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
                    "send_on": "2026-04-01",
                    "credit_cents": credit,
                    "amount_due_cents": plan_cents - credit,
                })

    def test_notice_calendar_boundaries(self):
        for renewal_on, send_on in [
            ("2020-01-01", "2019-12-18"),
            ("2024-03-14", "2024-02-29"),
            ("2024-02-29", "2024-02-15"),
            ("2025-03-01", "2025-02-15"),
            ("2099-12-31", "2099-12-17"),
        ]:
            with self.subTest(renewal_on=renewal_on):
                account = {
                    "customer_id": "member-日",
                    "renewal_on": renewal_on,
                    "plan_cents": 100,
                    "completed_years": 3,
                    "autopay": True,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "member-日",
                    "send_on": send_on,
                    "credit_cents": 15,
                    "amount_due_cents": 85,
                })


if __name__ == "__main__":
    unittest.main()
