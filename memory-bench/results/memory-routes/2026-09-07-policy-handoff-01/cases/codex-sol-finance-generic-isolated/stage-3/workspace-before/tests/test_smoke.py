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

    def test_quote_uses_release_1_by_default(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-low",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2020-01-01",
                    "charge_cents": 109,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-low",
                "credit_cents": 10,
                "amount_due_cents": 99,
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
                    "service_on": "2099-12-31",
                    "charge_cents": 50000,
                },
            },
            {
                "release": "1.0",
                "line_id": "L-cap",
                "credit_cents": 2400,
                "amount_due_cents": 47600,
            },
        )

    def test_empty_statement_total_uses_release_1_by_default(self):
        self.check_request(
            {"command": "total", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_total_shares_cap_across_an_accounts_lines(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S-1",
                        "service_on": "2026-05-02",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S-2",
                        "service_on": "2026-05-01",
                        "charge_cents": 10000,
                    },
                ],
            },
            {
                "release": "1.0",
                "credit_cents": 2400,
                "amount_due_cents": 27600,
            },
        )

    def test_total_gives_distinct_accounts_independent_caps(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {
                        "line_id": "L-a",
                        "account_id": "A",
                        "subscription_id": "shared",
                        "service_on": "2020-01-01",
                        "charge_cents": 30000,
                    },
                    {
                        "line_id": "L-b",
                        "account_id": "B",
                        "subscription_id": "shared",
                        "service_on": "2099-12-31",
                        "charge_cents": 30000,
                    },
                ],
            },
            {
                "release": "1.0",
                "credit_cents": 4800,
                "amount_due_cents": 55200,
            },
        )

    def test_total_rounds_each_line_before_adding_credit(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-01",
                        "charge_cents": 19,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-02",
                        "charge_cents": 19,
                    },
                ],
            },
            {
                "release": "1.0",
                "credit_cents": 2,
                "amount_due_cents": 36,
            },
        )
