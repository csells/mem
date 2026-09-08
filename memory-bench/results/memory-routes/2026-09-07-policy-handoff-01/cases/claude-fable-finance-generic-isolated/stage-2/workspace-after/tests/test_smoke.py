import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_ping(self):
        self.check_request({"command": "ping"}, {"status": "ok", "product": "Meridian Credits"})

    def test_unknown(self):
        self.check_request({"command": "unknown"}, {"error": "unknown_command"})

    def test_total_shares_cap_per_account(self):
        # Release 1.0: the 2400-cent cap is shared per account_id across
        # subscriptions, served earliest service_on first, ties by line_id.
        def line(line_id, account, sub, day, cents):
            return {"line_id": line_id, "account_id": account, "subscription_id": sub,
                    "service_on": day, "charge_cents": cents}
        lines = [
            line("L-3", "A", "S2", "2026-04-20", 20000),  # 2000 uncapped, cap left 400 -> 400
            line("L-1", "A", "S1", "2026-04-10", 10000),  # 1000
            line("L-2", "A", "S1", "2026-04-10", 10000),  # 1000
            line("L-4", "B", "S1", "2026-04-01", 30000),  # 3000 uncapped -> 2400 (own cap)
        ]
        # Credit: A = 1000 + 1000 + 400 = 2400; B = 2400. Charges = 70000.
        self.check_request({"command": "total", "lines": lines},
                           {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 65200})
