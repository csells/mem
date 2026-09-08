import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

LINE = {
    "line_id": "L-1",
    "account_id": "A",
    "subscription_id": "S",
    "service_on": "2026-04-15",
    "charge_cents": 19999,
}


class QuoteTests(unittest.TestCase):
    def run_cli(self, request):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        return json.loads(got.stdout)

    def check_quote(self, line, release=None):
        request = {"command": "quote", "line": line}
        if release is not None:
            request["release"] = release
        return self.run_cli(request)

    def test_explicit_release_1_0(self):
        got = self.check_quote(LINE, release="1.0")
        self.assertEqual(got, {"release": "1.0", "line_id": "L-1",
                               "credit_cents": 1999, "amount_due_cents": 18000})

    def test_explicit_release_2_0(self):
        got = self.check_quote(LINE, release="2.0")
        self.assertEqual(got, {"release": "2.0", "line_id": "L-1",
                               "credit_cents": 2999, "amount_due_cents": 17000})

    def test_omitted_release_selects_current(self):
        got = self.check_quote(LINE)
        self.assertEqual(got, {"release": "2.0", "line_id": "L-1",
                               "credit_cents": 2999, "amount_due_cents": 17000})

    def test_credit_rounded_down(self):
        got = self.check_quote({**LINE, "line_id": "L-2", "charge_cents": 19999})
        self.assertEqual(got["credit_cents"], 2999)

    def test_cap_limits_single_line(self):
        got = self.check_quote({**LINE, "line_id": "L-3", "charge_cents": 30000})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-3",
                               "credit_cents": 3000, "amount_due_cents": 27000})

    def test_credit_at_exact_cap_release_1_0(self):
        got = self.check_quote({**LINE, "line_id": "L-4", "charge_cents": 24000},
                               release="1.0")
        self.assertEqual(got["credit_cents"], 2400)
        self.assertEqual(got["amount_due_cents"], 21600)

    def test_credit_at_exact_cap_release_2_0(self):
        got = self.check_quote({**LINE, "line_id": "L-5", "charge_cents": 20000})
        self.assertEqual(got["credit_cents"], 3000)
        self.assertEqual(got["amount_due_cents"], 17000)

    def test_zero_charge(self):
        got = self.check_quote({**LINE, "line_id": "L-6", "charge_cents": 0})
        self.assertEqual(got, {"release": "2.0", "line_id": "L-6",
                               "credit_cents": 0, "amount_due_cents": 0})

    def test_unsupported_release(self):
        got = self.run_cli({"command": "quote", "release": "3.0", "line": LINE})
        self.assertEqual(got, {"error": "unsupported_release"})
