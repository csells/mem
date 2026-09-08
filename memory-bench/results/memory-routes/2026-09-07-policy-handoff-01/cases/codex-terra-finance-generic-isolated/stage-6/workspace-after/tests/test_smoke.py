import json
from pathlib import Path
import subprocess
import sys
import unittest

from main import credit_for_lines

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

    def test_current_total_caps_by_account_and_prioritizes_largest_charge(self):
        self.check_request(
            {
                "command": "total",
                "lines": [
                    {"line_id": "late", "account_id": "A", "subscription_id": "one",
                     "service_on": "2026-04-20", "charge_cents": 10000},
                    {"line_id": "first", "account_id": "A", "subscription_id": "two",
                     "service_on": "2026-04-01", "charge_cents": 30000},
                    {"line_id": "other", "account_id": "B", "subscription_id": "one",
                     "service_on": "2026-04-01", "charge_cents": 30000},
                ],
            },
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 64000},
        )

    def test_release_one_keeps_subscription_cap_and_date_priority(self):
        self.check_request(
            {
                "command": "total",
                "release": "1.0",
                "lines": [
                    {"line_id": "later", "account_id": "A", "subscription_id": "S",
                     "service_on": "2026-04-02", "charge_cents": 10000},
                    {"line_id": "earlier", "account_id": "A", "subscription_id": "S",
                     "service_on": "2026-04-01", "charge_cents": 23000},
                    {"line_id": "separate", "account_id": "A", "subscription_id": "T",
                     "service_on": "2026-04-02", "charge_cents": 10000},
                ],
            },
            {"release": "1.0", "credit_cents": 3400, "amount_due_cents": 39600},
        )

    def test_release_one_statement_preserves_order_and_empty_shape(self):
        self.check_request(
            {"command": "statement", "release": "1.0", "lines": []},
            {"release": "1.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0},
        )
        self.check_request(
            {
                "command": "statement",
                "release": "1.0",
                "lines": [
                    {"line_id": "later", "account_id": "A", "subscription_id": "S",
                     "service_on": "2026-04-02", "charge_cents": 10000},
                    {"line_id": "earlier", "account_id": "A", "subscription_id": "S",
                     "service_on": "2026-04-01", "charge_cents": 23000},
                ],
            },
            {
                "release": "1.0",
                "lines": [
                    {"line_id": "later", "credit_cents": 100, "amount_due_cents": 9900},
                    {"line_id": "earlier", "credit_cents": 2300, "amount_due_cents": 20700},
                ],
                "credit_cents": 2400,
                "amount_due_cents": 30600,
            },
        )

    def test_current_equal_charges_use_id_order_for_partial_cap(self):
        lines = [
            {"line_id": "z", "account_id": "A", "subscription_id": "S1",
             "service_on": "2026-01-01", "charge_cents": 19999},
            {"line_id": "a", "account_id": "A", "subscription_id": "S2",
             "service_on": "2026-01-02", "charge_cents": 19999},
        ]
        self.assertEqual(credit_for_lines(lines, "2.0"), {"a": 2999, "z": 1})
