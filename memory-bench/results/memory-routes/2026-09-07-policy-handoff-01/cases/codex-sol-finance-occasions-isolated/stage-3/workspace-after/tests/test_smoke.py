import json
from pathlib import Path
import subprocess
import sys
import unittest

from main import statement_credits

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

    def test_quote_defaults_to_current_release(self):
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
                "release": "2.0",
                "credit_cents": 2999,
                "amount_due_cents": 17000,
                "line_id": "L-1",
            },
        )

    def test_quote_supports_release_1(self):
        self.check_request(
            {
                "command": "quote",
                "release": "1.0",
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
                "credit_cents": 1999,
                "amount_due_cents": 18000,
                "line_id": "L-1",
            },
        )

    def test_empty_statement_total(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_release_1_total_caps_credits_by_account(self):
        lines = [
            {
                "line_id": "later",
                "account_id": "A",
                "subscription_id": "S-1",
                "service_on": "2026-02-01",
                "charge_cents": 20000,
            },
            {
                "line_id": "earlier",
                "account_id": "A",
                "subscription_id": "S-2",
                "service_on": "2026-01-01",
                "charge_cents": 10000,
            },
            {
                "line_id": "other-account",
                "account_id": "B",
                "subscription_id": "S-1",
                "service_on": "2026-03-01",
                "charge_cents": 5000,
            },
        ]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {
                "release": "1.0",
                "credit_cents": 2900,
                "amount_due_cents": 32100,
            },
        )

    def test_release_2_total_caps_by_account_and_subscription(self):
        lines = [
            {
                "line_id": "same-subscription-low",
                "account_id": "A",
                "subscription_id": "S-1",
                "service_on": "2026-01-01",
                "charge_cents": 10000,
            },
            {
                "line_id": "same-subscription-high",
                "account_id": "A",
                "subscription_id": "S-1",
                "service_on": "2026-02-01",
                "charge_cents": 20000,
            },
            {
                "line_id": "other-subscription",
                "account_id": "A",
                "subscription_id": "S-2",
                "service_on": "2026-03-01",
                "charge_cents": 5000,
            },
            {
                "line_id": "other-account",
                "account_id": "B",
                "subscription_id": "S-1",
                "service_on": "2026-04-01",
                "charge_cents": 5000,
            },
        ]
        self.check_request(
            {"command": "total", "lines": lines},
            {
                "release": "2.0",
                "credit_cents": 4500,
                "amount_due_cents": 35500,
            },
        )

    def test_release_2_assigns_cap_by_charge_then_line_id(self):
        lines = [
            {
                "line_id": "z-small",
                "account_id": "A",
                "subscription_id": "S",
                "service_on": "2026-01-01",
                "charge_cents": 10000,
            },
            {
                "line_id": "y-equal",
                "account_id": "A",
                "subscription_id": "S",
                "service_on": "2026-02-01",
                "charge_cents": 15000,
            },
            {
                "line_id": "x-equal",
                "account_id": "A",
                "subscription_id": "S",
                "service_on": "2026-03-01",
                "charge_cents": 15000,
            },
        ]

        self.assertEqual(
            statement_credits(lines, "2.0"),
            {"x-equal": 2250, "y-equal": 750, "z-small": 0},
        )
