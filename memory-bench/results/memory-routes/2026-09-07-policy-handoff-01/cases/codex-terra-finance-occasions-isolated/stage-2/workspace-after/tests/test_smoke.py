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

    def test_quote_uses_current_release_when_omitted(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-1",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-04-15",
                    "charge_cents": 19999,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-1",
                "credit_cents": 1999,
                "amount_due_cents": 18000,
            },
        )

    def test_quote_caps_single_line_credit(self):
        self.check_request(
            {
                "command": "quote",
                "release": "1.0",
                "line": {
                    "line_id": "L-cap",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-04-15",
                    "charge_cents": 30000,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-cap",
                "credit_cents": 2400,
                "amount_due_cents": 27600,
            },
        )

    def test_total_uses_one_shared_cap_in_service_then_id_order(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {"line_id": "Z", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-02", "charge_cents": 15000},
                    {"line_id": "B", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 15000},
                    {"line_id": "A", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 15000},
                ],
            },
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 42600},
        )

    def test_total_separates_subscription_groups_by_account(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {"line_id": "A-1", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 30000},
                    {"line_id": "B-1", "account_id": "B", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 30000},
                ],
            },
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200},
        )

    def test_total_allows_an_empty_statement(self):
        self.check_request(
            {"command": "total", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )
