import unittest

from main import handle


class QuoteTests(unittest.TestCase):
    def test_rounding_and_cap_for_explicit_release_1(self):
        for release in ("1.0",):
            for charge, credit in (
                (0, 0),
                (9, 0),
                (10, 1),
                (19999, 1999),
                (23999, 2399),
                (24000, 2400),
                (24010, 2400),
                (10**20, 2400),
            ):
                for service_on in ("2020-01-01", "2099-12-31"):
                    with self.subTest(release=release, charge=charge, date=service_on):
                        request = {
                            "command": "quote",
                            "line": {
                                "line_id": "renewal-\u03a9",
                                "account_id": "A",
                                "subscription_id": "S",
                                "service_on": service_on,
                                "charge_cents": charge,
                            },
                        }
                        if release is not None:
                            request["release"] = release
                        self.assertEqual(handle(request), {
                            "release": "1.0",
                            "line_id": "renewal-\u03a9",
                            "credit_cents": credit,
                            "amount_due_cents": charge - credit,
                        })
