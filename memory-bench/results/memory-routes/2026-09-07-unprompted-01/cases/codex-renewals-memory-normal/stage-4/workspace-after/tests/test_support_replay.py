import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import main


ROOT = Path(__file__).resolve().parents[1]


class SupportReplayTests(unittest.TestCase):
    def test_release_1_0_replay(self):
        cases = [
            (500, 2, True, "2026-04-15", "2026-03-25", 50),
            (19999, 2, True, "2026-04-15", "2026-03-25", 1999),
            (19999, 2, False, "2026-04-15", "2026-03-25", 0),
            (19999, 1, True, "2026-04-15", "2026-03-25", 0),
            (90000, 8, True, "2026-04-15", "2026-03-25", 2400),
            (23999, 2, True, "2026-04-15", "2026-03-25", 2399),
            (24000, 2, True, "2026-04-15", "2026-03-25", 2400),
            (24010, 2, True, "2026-04-15", "2026-03-25", 2400),
            (0, 2, True, "2020-01-01", "2019-12-11", 0),
            (9, 2, True, "2024-02-29", "2024-02-08", 0),
            (10, 2, True, "2024-03-21", "2024-02-29", 1),
            (100, 0, False, "2025-03-21", "2025-02-28", 0),
            (100, 2, True, "2099-12-31", "2099-12-10", 10),
        ]
        for plan, years, autopay, renewal_on, send_on, credit in cases:
            with self.subTest(plan=plan, years=years, autopay=autopay,
                              renewal_on=renewal_on):
                account = {
                    "customer_id": 'M-é,"\n', "renewal_on": renewal_on,
                    "plan_cents": plan, "completed_years": years, "autopay": autopay,
                }
                request = {"command": "support_replay", "case_id": "IOS-1842",
                           "account": account}
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")], input=json.dumps(request),
                    capture_output=True, text=True, check=True, timeout=3,
                )
                self.assertEqual(json.loads(result.stdout), {
                    "case_id": "IOS-1842",
                    "notice": {
                        "customer_id": account["customer_id"], "send_on": send_on,
                        "credit_cents": credit, "amount_due_cents": plan - credit,
                    },
                })

    def test_replay_is_independent_of_current_policy(self):
        account = {
            "customer_id": "M-17", "renewal_on": "2026-04-15",
            "plan_cents": 500, "completed_years": 2, "autopay": True,
        }
        with patch.object(main, "make_notice", side_effect=AssertionError("current policy")):
            self.assertEqual(main.handle({
                "command": "support_replay", "case_id": "IOS-1842", "account": account,
            }), {
                "case_id": "IOS-1842",
                "notice": {"customer_id": "M-17", "send_on": "2026-03-25",
                           "credit_cents": 50, "amount_due_cents": 450},
            })


if __name__ == "__main__":
    unittest.main()
