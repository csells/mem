import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTests(unittest.TestCase):
    def call(self, account):
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py")],
            input=json.dumps({
                "command": "compat_notice", "release": "1.0", "account": account,
            }),
            capture_output=True, text=True, check=True, timeout=3,
        )
        return json.loads(result.stdout)

    def test_original_release_credit_rules(self):
        # Expected values come from the release 1.0 requirements in trial-0fl.
        cases = [
            (19999, 2, True, 1999, 18000),
            (19999, 2, False, 0, 19999),
            (19999, 1, True, 0, 19999),
            (19999, 0, True, 0, 19999),
            (19999, 3, False, 0, 19999),
            (19999, 3, True, 1999, 18000),
            (90000, 8, True, 2400, 87600),
            (23999, 2, True, 2399, 21600),
            (24000, 2, True, 2400, 21600),
            (24010, 2, True, 2400, 21610),
            (0, 2, True, 0, 0),
            (9, 2, True, 0, 9),
            (10, 2, True, 1, 9),
            (10**30 + 9, 2, True, 2400, 10**30 - 2391),
        ]
        for plan, years, autopay, credit, due in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay):
                account = {
                    "customer_id": ' member,"雪\r\n ',
                    "renewal_on": "2026-04-15",
                    "plan_cents": plan,
                    "completed_years": years,
                    "autopay": autopay,
                }
                self.assertEqual(self.call(account), {
                    "release": "1.0",
                    "notice": {
                        "customer_id": ' member,"雪\r\n ',
                        "send_on": "2026-03-25",
                        "credit_cents": credit,
                        "amount_due_cents": due,
                    },
                })

    def test_original_release_calendar_boundaries(self):
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
                    "customer_id": "calendar-member", "renewal_on": renewal_on,
                    "plan_cents": 100, "completed_years": 2, "autopay": True,
                }), {
                    "release": "1.0",
                    "notice": {
                        "customer_id": "calendar-member", "send_on": send_on,
                        "credit_cents": 10, "amount_due_cents": 90,
                    },
                })


if __name__ == "__main__":
    unittest.main()
