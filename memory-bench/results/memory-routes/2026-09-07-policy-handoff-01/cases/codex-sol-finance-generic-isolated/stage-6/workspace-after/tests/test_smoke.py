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

    def test_quote_uses_release_2_by_default(self):
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
                "release": "2.0",
                "line_id": "L-low",
                "credit_cents": 16,
                "amount_due_cents": 93,
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

    def test_empty_statement_total_uses_release_2_by_default(self):
        self.check_request(
            {"command": "total", "lines": []},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0},
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
                "release": "1.0",
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
                "release": "1.0",
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

    def test_release_2_shares_cap_within_a_subscription(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-small",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2020-01-01",
                        "charge_cents": 10000,
                    },
                    {
                        "line_id": "L-large",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2099-12-31",
                        "charge_cents": 20000,
                    },
                ],
            },
            {
                "release": "2.0",
                "credit_cents": 3000,
                "amount_due_cents": 27000,
            },
        )

    def test_release_2_gives_distinct_subscriptions_independent_caps(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {
                        "line_id": "L-a",
                        "account_id": "A",
                        "subscription_id": "shared",
                        "service_on": "2026-05-01",
                        "charge_cents": 30000,
                    },
                    {
                        "line_id": "L-b",
                        "account_id": "B",
                        "subscription_id": "shared",
                        "service_on": "2026-05-01",
                        "charge_cents": 30000,
                    },
                    {
                        "line_id": "L-c",
                        "account_id": "A",
                        "subscription_id": "other",
                        "service_on": "2026-05-01",
                        "charge_cents": 30000,
                    },
                ],
            },
            {
                "release": "2.0",
                "credit_cents": 9000,
                "amount_due_cents": 81000,
            },
        )

    def test_release_2_rounds_each_line_before_adding_credit(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
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
                "release": "2.0",
                "credit_cents": 4,
                "amount_due_cents": 34,
            },
        )

    def test_empty_statement_uses_release_2_by_default(self):
        self.check_request(
            {"command": "statement", "lines": []},
            {
                "release": "2.0",
                "lines": [],
                "credit_cents": 0,
                "amount_due_cents": 0,
            },
        )

    def test_empty_release_1_statement(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": []},
            {
                "release": "1.0",
                "lines": [],
                "credit_cents": 0,
                "amount_due_cents": 0,
            },
        )

    def test_release_1_statement_uses_account_cap_and_priority(self):
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-later",
                        "account_id": "A",
                        "subscription_id": "S-1",
                        "service_on": "2026-05-02",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-earlier",
                        "account_id": "A",
                        "subscription_id": "S-2",
                        "service_on": "2026-05-01",
                        "charge_cents": 10000,
                    },
                ],
            },
            {
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-later",
                        "credit_cents": 1400,
                        "amount_due_cents": 18600,
                    },
                    {
                        "line_id": "L-earlier",
                        "credit_cents": 1000,
                        "amount_due_cents": 9000,
                    },
                ],
                "credit_cents": 2400,
                "amount_due_cents": 27600,
            },
        )

    def test_release_1_statement_breaks_date_ties_by_line_id(self):
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "z",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-01",
                        "charge_cents": 15000,
                    },
                    {
                        "line_id": "a",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-01",
                        "charge_cents": 15000,
                    },
                ],
            },
            {
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "z",
                        "credit_cents": 900,
                        "amount_due_cents": 14100,
                    },
                    {
                        "line_id": "a",
                        "credit_cents": 1500,
                        "amount_due_cents": 13500,
                    },
                ],
                "credit_cents": 2400,
                "amount_due_cents": 27600,
            },
        )

    def test_statement_displays_each_assigned_line_credit_in_input_order(self):
        self.check_request(
            {
                "command": "statement",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-small",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2020-01-01",
                        "charge_cents": 10000,
                    },
                    {
                        "line_id": "L-large",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2099-12-31",
                        "charge_cents": 20000,
                    },
                ],
            },
            {
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-small",
                        "credit_cents": 0,
                        "amount_due_cents": 10000,
                    },
                    {
                        "line_id": "L-large",
                        "credit_cents": 3000,
                        "amount_due_cents": 17000,
                    },
                ],
                "credit_cents": 3000,
                "amount_due_cents": 27000,
            },
        )

    def test_statement_breaks_equal_charge_priority_by_line_id(self):
        self.check_request(
            {
                "command": "statement",
                "lines": [
                    {
                        "line_id": "z",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-01",
                        "charge_cents": 15000,
                    },
                    {
                        "line_id": "a",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-05-02",
                        "charge_cents": 15000,
                    },
                ],
            },
            {
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "z",
                        "credit_cents": 750,
                        "amount_due_cents": 14250,
                    },
                    {
                        "line_id": "a",
                        "credit_cents": 2250,
                        "amount_due_cents": 12750,
                    },
                ],
                "credit_cents": 3000,
                "amount_due_cents": 27000,
            },
        )
