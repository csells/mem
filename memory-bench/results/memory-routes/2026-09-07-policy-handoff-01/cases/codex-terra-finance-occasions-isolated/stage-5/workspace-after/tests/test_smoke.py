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
                "release": "2.0",
                "line_id": "L-1",
                "credit_cents": 2999,
                "amount_due_cents": 17000,
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
                "release": "1.0",
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
            {"release": "2.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_release_2_shares_cap_by_account_and_prioritizes_larger_charges(self):
        self.check_request(
            {
                "command": "total",
                "release": "2.0",
                "lines": [
                    {"line_id": "low", "account_id": "A", "subscription_id": "S-1", "service_on": "2026-05-01", "charge_cents": 10000},
                    {"line_id": "high", "account_id": "A", "subscription_id": "S-2", "service_on": "2026-05-02", "charge_cents": 15000},
                    {"line_id": "other-account", "account_id": "B", "subscription_id": "S-1", "service_on": "2026-05-03", "charge_cents": 15000},
                ],
            },
            {"release": "2.0", "credit_cents": 5250, "amount_due_cents": 34750},
        )

    def test_release_2_uses_line_id_for_equal_charge_priority(self):
        import main

        credits = main.allocated_credits(
            [
                {"line_id": "Z", "account_id": "A", "subscription_id": "S-1", "service_on": "2026-05-01", "charge_cents": 15000},
                {"line_id": "A", "account_id": "A", "subscription_id": "S-2", "service_on": "2026-05-02", "charge_cents": 15000},
            ],
            "2.0",
        )
        self.assertEqual(credits, {"A": 2250, "Z": 750})

    def test_statement_preserves_input_order_and_matches_total(self):
        lines = [
            {"line_id": "low", "account_id": "A", "subscription_id": "S-1", "service_on": "2026-05-01", "charge_cents": 10000},
            {"line_id": "high", "account_id": "A", "subscription_id": "S-2", "service_on": "2026-05-02", "charge_cents": 15000},
            {"line_id": "other", "account_id": "B", "subscription_id": "S-1", "service_on": "2026-05-03", "charge_cents": 15000},
        ]
        self.check_request(
            {"command": "statement", "lines": lines},
            {
                "release": "2.0",
                "lines": [
                    {"line_id": "low", "credit_cents": 750, "amount_due_cents": 9250},
                    {"line_id": "high", "credit_cents": 2250, "amount_due_cents": 12750},
                    {"line_id": "other", "credit_cents": 2250, "amount_due_cents": 12750},
                ],
                "credit_cents": 5250,
                "amount_due_cents": 34750,
            },
        )

    def test_statement_allows_an_empty_statement(self):
        self.check_request(
            {"command": "statement", "lines": []},
            {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_release_1_statement_uses_subscription_cap_and_service_then_id_priority(self):
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {"line_id": "later", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-02", "charge_cents": 15000},
                    {"line_id": "B", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 15000},
                    {"line_id": "A", "account_id": "A", "subscription_id": "S", "service_on": "2026-05-01", "charge_cents": 15000},
                    {"line_id": "other", "account_id": "A", "subscription_id": "T", "service_on": "2026-05-01", "charge_cents": 30000},
                ],
            },
            {
                "release": "1.0",
                "lines": [
                    {"line_id": "later", "credit_cents": 0, "amount_due_cents": 15000},
                    {"line_id": "B", "credit_cents": 900, "amount_due_cents": 14100},
                    {"line_id": "A", "credit_cents": 1500, "amount_due_cents": 13500},
                    {"line_id": "other", "credit_cents": 2400, "amount_due_cents": 27600},
                ],
                "credit_cents": 4800,
                "amount_due_cents": 70200,
            },
        )
