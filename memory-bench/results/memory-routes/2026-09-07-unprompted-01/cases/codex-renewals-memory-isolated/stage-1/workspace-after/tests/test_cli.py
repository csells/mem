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
