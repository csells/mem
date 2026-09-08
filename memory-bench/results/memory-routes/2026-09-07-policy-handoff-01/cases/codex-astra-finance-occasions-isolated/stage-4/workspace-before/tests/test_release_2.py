import json
import subprocess
import sys
import unittest

from test_total import ROOT, line


class Release2Tests(unittest.TestCase):
    def check_total(self, lines, credit, due):
        self.check_request({"command": "total", "lines": lines}, {
            "credit_cents": credit, "amount_due_cents": due,
        })

    def check_request(self, request, expected):
        for release in (None, "2.0"):
            with self.subTest(release=release, request=request):
                payload = dict(request)
                if release is not None:
                    payload["release"] = release
                result = subprocess.run(
                    [sys.executable, str(ROOT / "main.py")],
                    input=json.dumps(payload), text=True, capture_output=True, check=True,
                )
                response = json.loads(result.stdout)
                self.assertEqual(response, {"release": "2.0", **expected})
                self.assertIs(type(response["credit_cents"]), int)
                self.assertIs(type(response["amount_due_cents"]), int)

    def test_empty_and_single_line(self):
        self.check_total([], 0, 0)
        self.check_total([line("L", "A", "S", 19999)], 2999, 17000)

    def test_caps_shared_within_account_subscription_pairs(self):
        lines = [
            line("é", "A", "S", 15000, "2099-12-31"),
            line("a", "A", "T", 10000, "2020-01-01"),
            line("😀", "A", "S", 10000),
            line("b", "B", "S", 30000),
        ]
        self.check_total(lines, 7500, 57500)
        self.check_total(list(reversed(lines)), 7500, 57500)

    def test_each_line_rounds_before_summing(self):
        self.check_total([
            line("1", "A", "S", 19),
            line("2", "A", "S", 19),
            line("3", "B", "T", 6),
            line("4", "B", "T", 0),
        ], 4, 40)

    def test_cap_boundary_and_large_integers(self):
        cases = ((0, 0), (6, 0), (7, 1), (19999, 2999),
                 (20000, 3000), (20007, 3000), (10**30 + 9, 3000))
        for charge, credit in cases:
            for date in ("2020-01-01", "2099-12-31"):
                charge_line = line("L-é-😀", "A", "S", charge, date)
                self.check_total([charge_line], credit, charge - credit)
                self.check_request({"command": "quote", "line": charge_line}, {
                    "line_id": "L-é-😀", "credit_cents": credit,
                    "amount_due_cents": charge - credit,
                })
