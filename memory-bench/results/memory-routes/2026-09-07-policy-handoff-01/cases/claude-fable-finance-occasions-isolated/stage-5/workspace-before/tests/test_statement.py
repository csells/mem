import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def line(line_id, account="A", subscription="S", service_on="2026-04-15", charge=1000):
    return {"line_id": line_id, "account_id": account, "subscription_id": subscription,
            "service_on": service_on, "charge_cents": charge}


def response_line(line_id, credit, due):
    return {"line_id": line_id, "credit_cents": credit, "amount_due_cents": due}


class StatementCliTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def test_one_line_example(self):
        got = self.run_cli({"command": "statement", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got, {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000,
                               "lines": [response_line("L-1", 2999, 17000)]})

    def test_explicit_release_2_0(self):
        got = self.run_cli({"command": "statement", "release": "2.0",
                            "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got["release"], "2.0")
        self.assertEqual(got["lines"], [response_line("L-1", 2999, 17000)])

    def test_empty_statement(self):
        got = self.run_cli({"command": "statement", "lines": []})
        self.assertEqual(got, {"release": "2.0", "lines": [], "credit_cents": 0, "amount_due_cents": 0})

    def test_response_has_exactly_the_specified_keys(self):
        got = self.run_cli({"command": "statement", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(set(got), {"release", "lines", "credit_cents", "amount_due_cents"})
        self.assertEqual(set(got["lines"][0]), {"line_id", "credit_cents", "amount_due_cents"})

    def test_preserves_input_order_while_priority_decides_credit(self):
        # Priority is largest charge first: L-a (12000) gets 1800, L-b (8000) gets the
        # remaining 1200, L-c (8000, later line_id) gets 0. Output stays in input order.
        lines = [line("L-c", charge=8000), line("L-b", charge=8000), line("L-a", charge=12000)]
        got = self.run_cli({"command": "statement", "lines": lines})
        self.assertEqual(got["lines"], [response_line("L-c", 0, 8000),
                                        response_line("L-b", 1200, 6800),
                                        response_line("L-a", 1800, 10200)])
        self.assertEqual(got["credit_cents"], 3000)
        self.assertEqual(got["amount_due_cents"], 25000)

    def test_cap_groups_are_per_subscription(self):
        lines = [line("L-1", subscription="S1", charge=30000),
                 line("L-2", subscription="S2", charge=30000),
                 line("L-3", account="B", subscription="S1", charge=30000)]
        got = self.run_cli({"command": "statement", "lines": lines})
        self.assertEqual(got["lines"], [response_line("L-1", 3000, 27000),
                                        response_line("L-2", 3000, 27000),
                                        response_line("L-3", 3000, 27000)])
        self.assertEqual(got["credit_cents"], 9000)

    def test_partial_remainder_on_a_line(self):
        lines = [line("L-1", charge=15000), line("L-2", charge=10000), line("L-3", charge=10000)]
        got = self.run_cli({"command": "statement", "lines": lines})
        self.assertEqual(got["lines"], [response_line("L-1", 2250, 12750),
                                        response_line("L-2", 750, 9250),
                                        response_line("L-3", 0, 10000)])

    def test_totals_match_total_command(self):
        lines = [line("L-1", charge=15000), line("L-2", subscription="S2", charge=7),
                 line("L-3", charge=10000), line("L-4", account="B", charge=50000)]
        for request in ({"lines": lines}, {"release": "2.0", "lines": lines},
                        {"release": "1.0", "lines": lines}):
            got = self.run_cli({"command": "statement", **request})
            expected = self.run_cli({"command": "total", **request})
            self.assertEqual({k: got[k] for k in expected}, expected)
            self.assertEqual(sum(l["credit_cents"] for l in got["lines"]), got["credit_cents"])
            self.assertEqual(sum(l["amount_due_cents"] for l in got["lines"]), got["amount_due_cents"])

    def test_explicit_release_1_0_uses_original_agreement(self):
        lines = [line("L-1", subscription="S1", charge=20000),
                 line("L-2", subscription="S2", service_on="2026-04-16", charge=20000)]
        got = self.run_cli({"command": "statement", "release": "1.0", "lines": lines})
        self.assertEqual(got, {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 37600,
                               "lines": [response_line("L-1", 2000, 18000),
                                         response_line("L-2", 400, 19600)]})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "statement", "release": "3.0", "lines": []})
        self.assertEqual(got, {"error": "unsupported_release"})

    def test_ping_and_unknown_command_preserved(self):
        self.assertEqual(self.run_cli({"command": "ping"}),
                         {"status": "ok", "product": "Meridian Credits"})
        self.assertEqual(self.run_cli({"command": "nope"}), {"error": "unknown_command"})


class StatementEngineTests(unittest.TestCase):
    def test_statement_uses_current_release_by_default(self):
        got = main.statement({"command": "statement", "lines": [line("L-1", charge=19999)]})
        self.assertEqual(got["release"], main.CURRENT_RELEASE)


if __name__ == "__main__":
    unittest.main()
