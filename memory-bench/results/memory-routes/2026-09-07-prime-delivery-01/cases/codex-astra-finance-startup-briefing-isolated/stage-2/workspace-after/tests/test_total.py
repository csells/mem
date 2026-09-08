import json
from pathlib import Path
import subprocess
import sys
import unittest

from main import handle


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
        for release in ({}, {"release": "1.0"}):
            with self.subTest(release=release):
                request = {"command": "total", "lines": lines, **release}
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps(request), text=True, capture_output=True,
                    check=True, timeout=5,
                )
                self.assertEqual(json.loads(proc.stdout), {
                    "release": "1.0", "credit_cents": credit,
                    "amount_due_cents": due,
                })

    def test_cap_is_shared_across_subscriptions_but_not_accounts(self):
        lines = [
            line("late", "A", "S", 20000, "2099-12-31"),
            line("early", "A", "T", 20000, "2020-01-01"),
            line("repeat", "A", "S", 20000),
            line("other", "B", "S", 30000),
        ]
        self.check_total(lines, 4800, 85200)
        self.check_total(list(reversed(lines)), 4800, 85200)

    def test_rounds_each_line_before_summing(self):
        self.check_total([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "A", "T", 9),
            line("4", "B", "S", 0),
        ], 2, 45)

    def test_cap_boundaries_and_large_integer_charges(self):
        for charge, credit in ((23999, 2399), (24000, 2400),
                               (24010, 2400), (10**30 + 9, 2400)):
            with self.subTest(charge=charge):
                self.check_total([line("1", "A", "S", charge)],
                                 credit, charge - credit)

    def test_cap_resets_for_each_request(self):
        request = {"command": "total", "lines": [line("1", "A", "S", 30000)]}
        expected = {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 27600}
        self.assertEqual(handle(request), expected)
        self.assertEqual(handle(request), expected)

    def test_empty_statement(self):
        self.check_total([], 0, 0)
