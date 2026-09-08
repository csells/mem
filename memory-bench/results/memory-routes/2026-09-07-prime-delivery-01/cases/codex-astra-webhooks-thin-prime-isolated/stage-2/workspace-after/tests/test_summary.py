import json
import subprocess
import sys
import unittest


class Summary(unittest.TestCase):
    def request(self, receipts, protocol):
        result = subprocess.run(
            [sys.executable, "main.py"],
            input=json.dumps({"command": "summary", "receipts": receipts, **protocol}),
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def test_cross_account_delivery_identity(self):
        receipts = [
            {"record_id": record_id, "account_id": account_id,
             "delivery_id": delivery_id, "occurred_at": occurred_at,
             "payload": payload}
            for record_id, account_id, delivery_id, occurred_at, payload in [
                ("R-1", "A", "D-1", "2026-04-02T00:30:00+02:00", "same"),
                ("R-2", "B", "D-1", "2026-04-01T22:30:00Z", "same"),
                ("R-3", "A", "D-1", "2026-04-01T20:00:00Z", "changed"),
                ("R-4", "B", "D-1", "2026-04-01T22:30:00Z", "changed"),
                ("R-5", "A", "D-2", "2026-04-01T22:30:00Z", "same"),
            ]
        ]
        for protocol in ({}, {"protocol": "1"}):
            for ordered in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, first=ordered[0]["record_id"]):
                    self.assertEqual(
                        self.request(ordered, protocol),
                        {"protocol": "1", "accepted_count": 3, "duplicate_count": 2},
                    )

    def test_empty_and_single_receipt(self):
        receipt = {
            "record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
            "occurred_at": "2026-04-01T22:30:00Z", "payload": "hello",
        }
        for protocol in ({}, {"protocol": "1"}):
            for receipts in ([], [receipt]):
                with self.subTest(protocol=protocol, receipts=receipts):
                    self.assertEqual(
                        self.request(receipts, protocol),
                        {"protocol": "1", "accepted_count": len(receipts), "duplicate_count": 0},
                    )
