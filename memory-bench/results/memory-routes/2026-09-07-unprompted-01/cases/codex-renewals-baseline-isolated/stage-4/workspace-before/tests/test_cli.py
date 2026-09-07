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
        ]
        for plan, years, autopay, credit in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay):
                account = {
                    "customer_id": "M-17",
                    "renewal_on": "2026-04-15",
                    "plan_cents": plan,
                    "completed_years": years,
                    "autopay": autopay,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "M-17",
                    "send_on": "2026-03-25",
                    "credit_cents": credit,
                    "amount_due_cents": plan - credit,
                })

    def test_support_replay_release_1_0_credit(self):
        cases = [
            (500, 2, True, 50, 450),
            (19999, 2, True, 1999, 18000),
            (19999, 2, False, 0, 19999),
            (19999, 1, True, 0, 19999),
            (19999, 0, False, 0, 19999),
            (90000, 8, True, 2400, 87600),
            (23999, 2, True, 2399, 21600),
            (24000, 2, True, 2400, 21600),
            (24010, 2, True, 2400, 21610),
            (0, 2, True, 0, 0),
            (9, 2, True, 0, 9),
        ]
        for plan, years, autopay, credit, due in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay):
                account = {
                    "customer_id": ' member,\"雪\n ',
                    "renewal_on": "2026-04-15",
                    "plan_cents": plan,
                    "completed_years": years,
                    "autopay": autopay,
                }
                self.assertEqual(self.call({
                    "command": "support_replay", "case_id": "IOS-1842",
                    "account": account,
                }), {
                    "case_id": "IOS-1842",
                    "notice": {
                        "customer_id": ' member,\"雪\n ',
                        "send_on": "2026-03-25",
                        "credit_cents": credit,
                        "amount_due_cents": due,
                    },
                })

    def test_support_replay_release_1_0_calendar_boundaries(self):
        cases = [
            ("2020-01-01", "2019-12-11"),
            ("2024-02-29", "2024-02-08"),
            ("2024-03-21", "2024-02-29"),
            ("2025-03-21", "2025-02-28"),
            ("2099-12-31", "2099-12-10"),
        ]
        for renewal_on, send_on in cases:
            with self.subTest(renewal_on=renewal_on):
                self.assertEqual(self.call({
                    "command": "support_replay", "case_id": "IOS-1842",
                    "account": {
                        "customer_id": "calendar-member", "renewal_on": renewal_on,
                        "plan_cents": 100, "completed_years": 2, "autopay": True,
                    },
                }), {
                    "case_id": "IOS-1842",
                    "notice": {
                        "customer_id": "calendar-member", "send_on": send_on,
                        "credit_cents": 10, "amount_due_cents": 90,
                    },
                })

    def test_export_empty(self):
        self.assertEqual(self.call({"command": "export", "accounts": []}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n",
            "count": 0,
        })

    def test_export_csv_quoting(self):
        cases = [
            ("M-17", "M-17"),
            ("comma,id", '"comma,id"'),
            ('quote"id', '"quote""id"'),
            ("cr\rid", '"cr\rid"'),
            ("lf\nid", '"lf\nid"'),
            ('all,\r\n"id', '"all,\r\n""id"'),
            (" space\t雪 ", " space\t雪 "),
        ]
        accounts = [{
            "customer_id": customer_id,
            "renewal_on": "2026-04-15",
            "plan_cents": 19999,
            "completed_years": 2,
            "autopay": True,
        } for customer_id, _ in cases]
        self.assertEqual(self.call({"command": "export", "accounts": accounts}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n" + "".join(
                encoded + ",2026-03-25,1999,18000\n" for _, encoded in cases
            ),
            "count": len(cases),
        })

    def test_export_preserves_rows_and_notice_values(self):
        accounts = [
            {"customer_id": "repeat", "renewal_on": "2020-01-01",
             "plan_cents": 90000, "completed_years": 8, "autopay": True},
            {"customer_id": "other", "renewal_on": "2024-03-21",
             "plan_cents": 0, "completed_years": 0, "autopay": False},
            {"customer_id": "repeat", "renewal_on": "2099-12-31",
             "plan_cents": 9, "completed_years": 1, "autopay": True},
        ]
        accounts.append(accounts[0].copy())
        self.assertEqual(self.call({"command": "export", "accounts": accounts}), {
            "csv": "customer_id,send_on,credit_cents,amount_due_cents\n"
                   "repeat,2019-12-11,2400,87600\n"
                   "other,2024-02-29,0,0\n"
                   "repeat,2099-12-10,0,9\n"
                   "repeat,2019-12-11,2400,87600\n",
            "count": 4,
        })

    def test_notice_calendar_boundaries(self):
        cases = [
            ("2020-01-01", "2019-12-11"),
            ("2024-02-29", "2024-02-08"),
            ("2024-03-21", "2024-02-29"),
            ("2025-03-21", "2025-02-28"),
            ("2099-12-31", "2099-12-10"),
        ]
        for renewal_on, send_on in cases:
            with self.subTest(renewal_on=renewal_on):
                account = {
                    "customer_id": "calendar-member",
                    "renewal_on": renewal_on,
                    "plan_cents": 100,
                    "completed_years": 2,
                    "autopay": True,
                }
                self.assertEqual(self.call({"command": "notice", "account": account}), {
                    "customer_id": "calendar-member",
                    "send_on": send_on,
                    "credit_cents": 10,
                    "amount_due_cents": 90,
                })


if __name__ == "__main__":
    unittest.main()
