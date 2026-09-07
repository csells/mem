import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompatibilityNoticeTests(unittest.TestCase):
    def test_original_release_receipts(self):
        # Expected values follow the original customer-facing issue trial-52b.
        cases = [
            (19999, 2, True, "2026-04-15", "2026-03-25", 1999),
            (19999, 3, False, "2026-04-15", "2026-03-25", 0),
            (19999, 1, True, "2026-04-15", "2026-03-25", 0),
            (19999, 0, True, "2026-04-15", "2026-03-25", 0),
            (90000, 8, True, "2026-04-15", "2026-03-25", 2400),
            (23999, 2, True, "2026-04-15", "2026-03-25", 2399),
            (24000, 2, True, "2026-04-15", "2026-03-25", 2400),
            (24010, 2, True, "2026-04-15", "2026-03-25", 2400),
            (0, 2, True, "2020-01-01", "2019-12-11", 0),
            (9, 2, True, "2024-02-29", "2024-02-08", 0),
            (10, 2, True, "2024-03-21", "2024-02-29", 1),
            (100, 2, True, "2025-03-21", "2025-02-28", 10),
            (10**30 + 1, 3, True, "2099-12-31", "2099-12-10", 2400),
        ]
        for plan, years, autopay, renewal_on, send_on, credit in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay,
                              renewal_on=renewal_on):
                account = {
                    "customer_id": 'M-é,"\n', "renewal_on": renewal_on,
                    "plan_cents": plan, "completed_years": years, "autopay": autopay,
                }
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps({"command": "compat_notice", "release": "1.0",
                                      "account": account}),
                    capture_output=True, text=True, check=True, timeout=3,
                )
                self.assertEqual(json.loads(result.stdout), {
                    "release": "1.0",
                    "notice": {
                        "customer_id": account["customer_id"], "send_on": send_on,
                        "credit_cents": credit, "amount_due_cents": plan - credit,
                    },
                })


if __name__ == "__main__":
    unittest.main()
