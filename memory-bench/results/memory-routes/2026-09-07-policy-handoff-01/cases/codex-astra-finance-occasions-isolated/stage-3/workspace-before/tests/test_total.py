import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account, subscription, charge, service_on="2026-04-15"):
    return {
        "line_id": line_id,
        "account_id": account,
        "subscription_id": subscription,
        "service_on": service_on,
        "charge_cents": charge,
    }


class TotalTests(unittest.TestCase):
    def check_total(self, lines, credit, due):
        for release in (None, "1.0"):
            with self.subTest(release=release):
                request = {"command": "total", "lines": lines}
                if release is not None:
                    request["release"] = release
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps(request), text=True,
                    capture_output=True, check=True,
                )
                response = json.loads(result.stdout)
                self.assertEqual(response, {
                    "release": "1.0",
                    "credit_cents": credit,
                    "amount_due_cents": due,
                })
                self.assertIs(type(response["credit_cents"]), int)
                self.assertIs(type(response["amount_due_cents"]), int)

    def test_empty_and_single_line(self):
        self.check_total([], 0, 0)
        self.check_total([line("L", "A", "S", 19999)], 1999, 18000)

    def test_account_caps_span_subscriptions_and_lines(self):
        lines = [
            line("é", "A", "S", 15000, "2099-12-31"),
            line("a", "A", "T", 10000, "2020-01-01"),
            line("😀", "A", "S", 5000),
            line("b", "B", "S", 30000),
        ]
        self.check_total(lines, 4800, 55200)
        self.check_total(list(reversed(lines)), 4800, 55200)

    def test_each_line_rounds_before_summing(self):
        self.check_total([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "B", "T", 9),
            line("4", "B", "T", 0),
        ], 2, 45)

    def test_cap_boundary_and_large_integers(self):
        for charge, credit in ((23999, 2399), (24000, 2400), (10**30 + 9, 2400)):
            with self.subTest(charge=charge):
                self.check_total([line("L", "A", "S", charge)], credit, charge - credit)
