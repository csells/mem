import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account_id, subscription_id, service_on, charge_cents):
    return {
        "line_id": line_id,
        "account_id": account_id,
        "subscription_id": subscription_id,
        "service_on": service_on,
        "charge_cents": charge_cents,
    }


class TotalTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_total_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_total_omitted_release_selects_current_agreement(self):
        self.check_request(
            {"command": "total", "lines": [
                line("L-1", "A", "S", "2026-04-15", 19999),
            ]},
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_total_shares_one_cap_per_account_across_lines(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                line("L-1", "A", "S1", "2026-04-01", 30000),
                line("L-2", "A", "S2", "2026-04-02", 30000),
                line("L-3", "A", "S1", "2026-04-03", 30000),
            ]},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 87600},
        )

    def test_total_caps_each_account_independently(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                line("L-1", "A", "S", "2026-04-01", 30000),
                line("L-2", "B", "S", "2026-04-01", 30000),
            ]},
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200},
        )

    def test_total_rounds_credit_down_per_line_before_the_cap(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [
                line("L-1", "A", "S", "2026-04-01", 15),
                line("L-2", "A", "S", "2026-04-02", 15),
            ]},
            {"release": "1.0", "credit_cents": 2, "amount_due_cents": 28},
        )

    def test_total_unsupported_release(self):
        self.check_request(
            {"command": "total", "release": "9.9", "lines": []},
            {"error": "unsupported_release"},
        )


if __name__ == "__main__":
    unittest.main()
