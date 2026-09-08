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

    def test_quote_example(self):
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
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000, "line_id": "L-1"},
        )

    def test_quote_release_2_example(self):
        self.check_request(
            {
                "command": "quote",
                "release": "2.0",
                "line": {
                    "line_id": "L-1",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-04-15",
                    "charge_cents": 19999,
                },
            },
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000, "line_id": "L-1"},
        )

    def test_quote_release_2_cap(self):
        self.check_request(
            {
                "command": "quote",
                "release": "2.0",
                "line": {
                    "line_id": "L-2",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-05-01",
                    "charge_cents": 50000,
                },
            },
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 47000, "line_id": "L-2"},
        )

    def test_quote_without_release_reports_current(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-2",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-05-01",
                    "charge_cents": 50000,
                },
            },
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 47000, "line_id": "L-2"},
        )

    def test_quote_zero_charge(self):
        self.check_request(
            {
                "command": "quote",
                "line": {
                    "line_id": "L-0",
                    "account_id": "A",
                    "subscription_id": "S",
                    "service_on": "2026-05-01",
                    "charge_cents": 0,
                },
            },
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0, "line_id": "L-0"},
        )

    def test_total_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_total_quote_example_line(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-15",
                        "charge_cents": 19999,
                    }
                ],
            },
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_total_cap_spans_subscriptions_of_one_account(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S1",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S2",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                ],
            },
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600},
        )

    def test_total_cap_is_per_account(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-01",
                        "charge_cents": 50000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "B",
                        "subscription_id": "S",
                        "service_on": "2026-04-02",
                        "charge_cents": 50000,
                    },
                ],
            },
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 95200},
        )

    def test_total_ties_break_by_line_id_regardless_of_input_order(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-b",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 24000,
                    },
                    {
                        "line_id": "L-a",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 500,
                    },
                ],
            },
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 22100},
        )

    def test_total_release_2_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": []},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_total_release_2_quote_example_line(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-15",
                        "charge_cents": 19999,
                    }
                ],
            },
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_total_release_2_cap_is_per_subscription(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S1",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S2",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                ],
            },
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 34000},
        )

    def test_total_release_2_same_subscription_different_accounts(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "B",
                        "subscription_id": "S",
                        "service_on": "2026-04-02",
                        "charge_cents": 20000,
                    },
                ],
            },
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 34000},
        )

    def test_total_release_2_largest_charge_first_then_remaining(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-01",
                        "charge_cents": 10000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 12000,
                    },
                ],
            },
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 19000},
        )

    def test_total_release_2_ties_break_by_line_id_regardless_of_input_order(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-b",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 24000,
                    },
                    {
                        "line_id": "L-a",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 24000,
                    },
                ],
            },
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 45000},
        )

    def test_total_without_release_reports_current(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-15",
                        "charge_cents": 19999,
                    }
                ],
            },
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_statement_empty(self):
        self.check_request(
            {"command": "statement", "lines": []},
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0, "lines": []},
        )

    def test_statement_release_2_one_line(self):
        self.check_request(
            {
                "command": "statement",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-15",
                        "charge_cents": 19999,
                    }
                ],
            },
            {
                "release": "2.0",
                "credit_cents": 2999,
                "amount_due_cents": 17000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 2999, "amount_due_cents": 17000}
                ],
            },
        )

    def test_statement_release_2_preserves_input_order_and_shares_cap(self):
        self.check_request(
            {
                "command": "statement",
                "release": "2.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-01",
                        "charge_cents": 10000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-03-01",
                        "charge_cents": 12000,
                    },
                ],
            },
            {
                "release": "2.0",
                "credit_cents": 3000,
                "amount_due_cents": 19000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 1200, "amount_due_cents": 8800},
                    {"line_id": "L-2", "credit_cents": 1800, "amount_due_cents": 10200},
                ],
            },
        )

    def test_statement_release_1_empty(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0, "lines": []},
        )

    def test_statement_release_1_one_line_receipt(self):
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S",
                        "service_on": "2026-04-15",
                        "charge_cents": 19999,
                    }
                ],
            },
            {
                "release": "1.0",
                "credit_cents": 1999,
                "amount_due_cents": 18000,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 1999, "amount_due_cents": 18000}
                ],
            },
        )

    def test_statement_release_1_earliest_service_first(self):
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {
                        "line_id": "L-1",
                        "account_id": "A",
                        "subscription_id": "S1",
                        "service_on": "2026-04-01",
                        "charge_cents": 20000,
                    },
                    {
                        "line_id": "L-2",
                        "account_id": "A",
                        "subscription_id": "S2",
                        "service_on": "2026-03-01",
                        "charge_cents": 20000,
                    },
                ],
            },
            {
                "release": "1.0",
                "credit_cents": 2400,
                "amount_due_cents": 37600,
                "lines": [
                    {"line_id": "L-1", "credit_cents": 400, "amount_due_cents": 19600},
                    {"line_id": "L-2", "credit_cents": 2000, "amount_due_cents": 18000},
                ],
            },
        )
