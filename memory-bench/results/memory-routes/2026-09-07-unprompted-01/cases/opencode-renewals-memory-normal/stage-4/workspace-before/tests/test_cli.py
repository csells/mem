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
        
    def test_support_replay(self):
        # Test the IOS-1842 case
        request = {
            "command": "support_replay",
            "case_id": "IOS-1842",
            "account": {
                "customer_id": "M-17",
                "renewal_on": "2026-04-15",
                "plan_cents": 500,
                "completed_years": 2,
                "autopay": True
            }
        }
        expected = {
            "case_id": "IOS-1842",
            "notice": {
                "customer_id": "M-17",
                "send_on": "2026-03-25",
                "credit_cents": 50,
                "amount_due_cents": 450
            }
        }
        self.assertEqual(self.call(request), expected)
        
    def test_support_replay_unsupported_case(self):
        # Test unsupported case
        request = {
            "command": "support_replay",
            "case_id": "IOS-1843",
            "account": {
                "customer_id": "M-17",
                "renewal_on": "2026-04-15",
                "plan_cents": 500,
                "completed_years": 2,
                "autopay": True
            }
        }
        expected = {"error": "unsupported_case"}
        self.assertEqual(self.call(request), expected)


if __name__ == "__main__":
    unittest.main()
