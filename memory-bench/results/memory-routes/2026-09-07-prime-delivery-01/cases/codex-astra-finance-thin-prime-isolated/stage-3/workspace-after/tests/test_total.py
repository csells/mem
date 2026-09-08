import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def line(line_id, account_id, subscription_id, charge_cents, service_on="2026-04-15"):
    return dict(line_id=line_id, account_id=account_id,
                subscription_id=subscription_id, charge_cents=charge_cents,
                service_on=service_on)


class TotalTests(unittest.TestCase):
    def check_total(self, lines, credit_cents, amount_due_cents):
        for release in ("1.0",):
            for ordered_lines in (lines, list(reversed(lines))):
                with self.subTest(release=release, lines=ordered_lines):
                    request = {"command": "total", "lines": ordered_lines}
                    if release is not None:
                        request["release"] = release
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "main.py")],
                        input=json.dumps(request), text=True,
                        capture_output=True, check=True,
                    )
                    self.assertEqual(json.loads(result.stdout), {
                        "release": "1.0", "credit_cents": credit_cents,
                        "amount_due_cents": amount_due_cents,
                    })

    def test_empty_and_single_line(self):
        self.check_total([], 0, 0)
        self.check_total([line("L", "A", "S", 19999)], 1999, 18000)

    def test_cap_shared_across_subscriptions_and_repeated_lines(self):
        self.check_total([
            line("Ω", "A", "S1", 10000, "2099-12-31"),
            line("a", "A", "S2", 10000, "2020-01-01"),
            line("Z", "A", "S1", 10000, "2020-01-01"),
        ], 2400, 27600)

    def test_accounts_have_independent_caps_even_with_same_subscription_id(self):
        self.check_total([
            line("1", "A", "S", 30000),
            line("2", "B", "S", 20000),
            line("3", "B", "S", 10000),
            line("4", "C", "S", 19999),
        ], 6799, 73200)

    def test_round_each_line_before_summing(self):
        self.check_total([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "A", "T", 9),
            line("4", "B", "S", 0),
        ], 2, 45)

    def test_cap_boundaries_and_large_integer(self):
        self.check_total([
            line("1", "A", "S", 23999),
            line("2", "A", "S", 9),
        ], 2399, 21609)
        self.check_total([
            line("1", "A", "S", 23999),
            line("2", "A", "T", 10),
        ], 2400, 21609)
        self.check_total([line("1", "A", "S", 10**30 + 9)],
                         2400, 10**30 - 2391)
