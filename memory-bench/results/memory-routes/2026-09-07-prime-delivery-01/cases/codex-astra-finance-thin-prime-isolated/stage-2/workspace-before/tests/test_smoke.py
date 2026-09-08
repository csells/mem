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

    def test_quote_rounding_and_cap(self):
        cases = [
            (0, 0),
            (9, 0),
            (10, 1),
            (19999, 1999),
            (23999, 2399),
            (24000, 2400),
            (24010, 2400),
            (10**30 + 9, 2400),
        ]
        for release in (None, "1.0"):
            for service_on in ("2020-01-01", "2099-12-31"):
                for charge_cents, credit_cents in cases:
                    with self.subTest(release=release, service_on=service_on,
                                      charge_cents=charge_cents):
                        request = {
                            "command": "quote",
                            "line": {
                                "line_id": "L-\u03a9",
                                "account_id": "A",
                                "subscription_id": "S",
                                "service_on": service_on,
                                "charge_cents": charge_cents,
                            },
                        }
                        if release is not None:
                            request["release"] = release
                        self.check_request(request, {
                            "release": "1.0",
                            "line_id": "L-\u03a9",
                            "credit_cents": credit_cents,
                            "amount_due_cents": charge_cents - credit_cents,
                        })
