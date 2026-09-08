import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_total import line

ROOT = Path(__file__).resolve().parents[1]


class Release2Tests(unittest.TestCase):
    def check_request(self, request, expected):
        for release in (None, "2.0"):
            with self.subTest(release=release, request=request):
                payload = dict(request)
                if release is not None:
                    payload["release"] = release
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps(payload), text=True,
                    capture_output=True, check=True,
                )
                self.assertEqual(json.loads(result.stdout),
                                 dict(release="2.0", **expected))

    def check_total(self, lines, credit_cents, amount_due_cents):
        for ordered_lines in (lines, list(reversed(lines))):
            self.check_request({"command": "total", "lines": ordered_lines}, {
                "credit_cents": credit_cents, "amount_due_cents": amount_due_cents,
            })

    def test_quote_and_single_line_total_boundaries(self):
        for charge, credit in ((0, 0), (6, 0), (7, 1), (19, 2),
                               (19999, 2999), (20000, 3000), (20007, 3000),
                               (10**30 + 9, 3000)):
            for date in ("2020-01-01", "2099-12-31"):
                charge_line = line("Ω", "A", "S", charge, date)
                self.check_request({"command": "quote", "line": charge_line}, {
                    "line_id": "Ω", "credit_cents": credit,
                    "amount_due_cents": charge - credit,
                })
                self.check_total([charge_line], credit, charge - credit)

    def test_empty(self):
        self.check_total([], 0, 0)

    def test_subscription_caps_and_account_identity(self):
        self.check_total([
            line("Ω", "A", "S", 10000, "2099-12-31"),
            line("a", "A", "S", 15000, "2020-01-01"),
            line("Z", "A", "T", 20000),
            line("b", "B", "S", 30000),
            line("c", "C", "S", 19999),
        ], 11999, 83000)

    def test_floor_each_line_before_summing(self):
        self.check_total([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "A", "S", 6),
            line("4", "B", "S", 0),
        ], 4, 40)

    def test_shared_cap_boundary(self):
        self.check_total([
            line("1", "A", "S", 19999),
            line("2", "A", "S", 6),
        ], 2999, 17006)
        self.check_total([
            line("1", "A", "S", 19999),
            line("2", "A", "S", 7),
        ], 3000, 17006)
