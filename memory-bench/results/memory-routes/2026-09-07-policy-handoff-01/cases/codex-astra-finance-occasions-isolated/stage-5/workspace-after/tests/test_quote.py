import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QuoteTests(unittest.TestCase):
    def test_rounding_cap_and_release_selection(self):
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
        for release in ("1.0",):
            for service_on in ("2020-01-01", "2099-12-31"):
                for charge, credit in cases:
                    with self.subTest(release=release, date=service_on, charge=charge):
                        request = {
                            "command": "quote",
                            "line": {
                                "line_id": "L-é-😀",
                                "account_id": "A",
                                "subscription_id": "S",
                                "service_on": service_on,
                                "charge_cents": charge,
                            },
                        }
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
                            "line_id": "L-é-😀",
                            "credit_cents": credit,
                            "amount_due_cents": charge - credit,
                        })
                        self.assertIs(type(response["credit_cents"]), int)
                        self.assertIs(type(response["amount_due_cents"]), int)
