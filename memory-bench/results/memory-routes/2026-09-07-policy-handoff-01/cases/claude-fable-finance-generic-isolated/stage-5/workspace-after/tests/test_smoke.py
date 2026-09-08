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

    @staticmethod
    def line(line_id, account, sub, day, cents):
        return {"line_id": line_id, "account_id": account, "subscription_id": sub,
                "service_on": day, "charge_cents": cents}

    def test_ping(self):
        self.check_request({"command": "ping"}, {"status": "ok", "product": "Meridian Credits"})

    def test_unknown(self):
        self.check_request({"command": "unknown"}, {"error": "unknown_command"})

    def test_release_1_total_shares_cap_per_account(self):
        # Release 1.0: the 2400-cent cap is shared per account_id across
        # subscriptions, served earliest service_on first, ties by line_id.
        lines = [
            self.line("L-3", "A", "S2", "2026-04-20", 20000),  # 2000 uncapped, cap left 400 -> 400
            self.line("L-1", "A", "S1", "2026-04-10", 10000),  # 1000
            self.line("L-2", "A", "S1", "2026-04-10", 10000),  # 1000
            self.line("L-4", "B", "S1", "2026-04-01", 30000),  # 3000 uncapped -> 2400 (own cap)
        ]
        # Credit: A = 1000 + 1000 + 400 = 2400; B = 2400. Charges = 70000.
        self.check_request({"command": "total", "release": "1.0", "lines": lines},
                           {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 65200})

    def test_omitted_release_is_2_0(self):
        # Current agreement is release 2.0: 15%, floored per line. Explicit
        # "2.0" behaves the same.
        line = self.line("L-1", "A", "S", "2026-04-15", 19999)
        expected = {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000,
                    "line_id": "L-1"}
        self.check_request({"command": "quote", "line": line}, expected)
        self.check_request({"command": "quote", "release": "2.0", "line": line}, expected)

    def test_release_2_total_shares_cap_per_subscription(self):
        # Release 2.0: the 3000-cent cap is shared per (account_id,
        # subscription_id); the same subscription_id under another account
        # is a separate group. Served largest charge first; service dates
        # never affect priority.
        lines = [
            self.line("L-2", "A", "S1", "2026-04-01", 10000),  # 1500 uncapped
            self.line("L-1", "A", "S1", "2026-04-30", 10000),  # 1500 uncapped
            self.line("L-3", "A", "S1", "2026-04-10", 20000),  # 3000 uncapped
            self.line("L-4", "A", "S2", "2026-04-10", 4000),   # 600, own group -> 600
            self.line("L-5", "B", "S1", "2026-04-10", 30000),  # 4500 uncapped, own group -> 3000
        ]
        # Group (A,S1): L-3 (largest) -> 3000, cap exhausted; L-1 -> 0; L-2 -> 0.
        # Group (A,S2): 600. Group (B,S1): 3000. Total credit 6600; charges 74000.
        self.check_request({"command": "total", "lines": lines},
                           {"release": "2.0", "credit_cents": 6600, "amount_due_cents": 67400})

    def test_release_2_tie_uses_line_id(self):
        # Equal charges in one group are served in increasing line_id order.
        lines = [
            self.line("L-b", "A", "S", "2026-04-01", 12000),  # 1800 uncapped, served second
            self.line("L-a", "A", "S", "2026-04-30", 12000),  # 1800 uncapped, served first
        ]
        # L-a -> 1800; L-b -> min(1800, 1200) = 1200. Total 3000; charges 24000.
        self.check_request({"command": "total", "release": "2.0", "lines": lines},
                           {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 21000})
        # Quoting either line alone is the whole statement, so it is uncapped.
        self.check_request({"command": "quote", "line": lines[0]},
                           {"release": "2.0", "credit_cents": 1800, "amount_due_cents": 10200,
                            "line_id": "L-b"})

    def test_statement_empty(self):
        expected = {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0}
        self.check_request({"command": "statement", "lines": []}, expected)
        self.check_request({"command": "statement", "release": "2.0", "lines": []}, expected)

    def test_statement_one_line(self):
        line = self.line("L-1", "A", "S", "2026-04-15", 19999)
        self.check_request({"command": "statement", "lines": [line]},
                           {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000,
                            "lines": [{"line_id": "L-1", "credit_cents": 2999,
                                       "amount_due_cents": 17000}]})

    def test_statement_shows_capped_lines_in_input_order(self):
        # Same input as the release 2.0 total test: per-line credits follow
        # the cap/priority engine, but the response keeps the input order
        # and its totals equal total's for the same input.
        lines = [
            self.line("L-2", "A", "S1", "2026-04-01", 10000),
            self.line("L-1", "A", "S1", "2026-04-30", 10000),
            self.line("L-3", "A", "S1", "2026-04-10", 20000),
            self.line("L-4", "A", "S2", "2026-04-10", 4000),
            self.line("L-5", "B", "S1", "2026-04-10", 30000),
        ]
        self.check_request({"command": "statement", "lines": lines}, {
            "release": "2.0", "credit_cents": 6600, "amount_due_cents": 67400,
            "lines": [
                {"line_id": "L-2", "credit_cents": 0, "amount_due_cents": 10000},
                {"line_id": "L-1", "credit_cents": 0, "amount_due_cents": 10000},
                {"line_id": "L-3", "credit_cents": 3000, "amount_due_cents": 17000},
                {"line_id": "L-4", "credit_cents": 600, "amount_due_cents": 3400},
                {"line_id": "L-5", "credit_cents": 3000, "amount_due_cents": 27000},
            ]})
        self.check_request({"command": "total", "lines": lines},
                           {"release": "2.0", "credit_cents": 6600, "amount_due_cents": 67400})

    def test_statement_tie_uses_line_id(self):
        lines = [
            self.line("L-b", "A", "S", "2026-04-01", 12000),
            self.line("L-a", "A", "S", "2026-04-30", 12000),
        ]
        self.check_request({"command": "statement", "release": "2.0", "lines": lines}, {
            "release": "2.0", "credit_cents": 3000, "amount_due_cents": 21000,
            "lines": [
                {"line_id": "L-b", "credit_cents": 1200, "amount_due_cents": 10800},
                {"line_id": "L-a", "credit_cents": 1800, "amount_due_cents": 10200},
            ]})

    def test_release_1_statement_empty(self):
        self.check_request({"command": "statement", "release": "1.0", "lines": []},
                           {"release": "1.0", "lines": [], "credit_cents": 0,
                            "amount_due_cents": 0})

    def test_release_1_statement_one_line(self):
        # The original quote example as a one-line release 1.0 receipt: 10%
        # floored per line.
        line = self.line("L-1", "A", "S", "2026-04-15", 19999)
        self.check_request({"command": "statement", "release": "1.0", "lines": [line]},
                           {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000,
                            "lines": [{"line_id": "L-1", "credit_cents": 1999,
                                       "amount_due_cents": 18000}]})

    def test_release_1_statement_shares_cap_per_account_in_input_order(self):
        # Same input as the release 1.0 total test: the 2400-cent cap is
        # shared per account_id across subscriptions, served earliest
        # service_on first (ties by line_id), yet the response keeps the
        # input order and its totals equal total's for the same input.
        lines = [
            self.line("L-3", "A", "S2", "2026-04-20", 20000),
            self.line("L-1", "A", "S1", "2026-04-10", 10000),
            self.line("L-2", "A", "S1", "2026-04-10", 10000),
            self.line("L-4", "B", "S1", "2026-04-01", 30000),
        ]
        self.check_request({"command": "statement", "release": "1.0", "lines": lines}, {
            "release": "1.0", "credit_cents": 4800, "amount_due_cents": 65200,
            "lines": [
                {"line_id": "L-3", "credit_cents": 400, "amount_due_cents": 19600},
                {"line_id": "L-1", "credit_cents": 1000, "amount_due_cents": 9000},
                {"line_id": "L-2", "credit_cents": 1000, "amount_due_cents": 9000},
                {"line_id": "L-4", "credit_cents": 2400, "amount_due_cents": 27600},
            ]})
        self.check_request({"command": "total", "release": "1.0", "lines": lines},
                           {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 65200})

    def test_release_1_statement_differs_from_release_2(self):
        # Under release 1.0 the earliest service date wins the account cap;
        # under release 2.0 the largest charge wins the subscription cap.
        lines = [
            self.line("L-big", "A", "S1", "2026-04-30", 30000),
            self.line("L-early", "A", "S2", "2026-04-01", 10000),
        ]
        self.check_request({"command": "statement", "release": "1.0", "lines": lines}, {
            "release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600,
            "lines": [
                {"line_id": "L-big", "credit_cents": 1400, "amount_due_cents": 28600},
                {"line_id": "L-early", "credit_cents": 1000, "amount_due_cents": 9000},
            ]})
        self.check_request({"command": "statement", "lines": lines}, {
            "release": "2.0", "credit_cents": 4500, "amount_due_cents": 35500,
            "lines": [
                {"line_id": "L-big", "credit_cents": 3000, "amount_due_cents": 27000},
                {"line_id": "L-early", "credit_cents": 1500, "amount_due_cents": 8500},
            ]})

    def test_unsupported_release(self):
        self.check_request({"command": "total", "release": "3.0", "lines": []},
                           {"error": "unsupported_release"})
        self.check_request({"command": "statement", "release": "3.0", "lines": []},
                           {"error": "unsupported_release"})
