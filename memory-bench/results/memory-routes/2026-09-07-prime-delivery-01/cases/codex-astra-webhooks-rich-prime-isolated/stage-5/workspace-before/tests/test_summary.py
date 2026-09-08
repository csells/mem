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
            {"record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-02T00:30:00+02:00", "payload": "first"},
            {"record_id": "R-2", "account_id": "B", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T22:30:00Z", "payload": "first"},
            {"record_id": "R-3", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T21:00:00Z", "payload": "changed"},
            {"record_id": "R-4", "account_id": "B", "delivery_id": "D-2",
             "occurred_at": "2026-04-01T21:00:00Z", "payload": "first"},
            {"record_id": "R-5", "account_id": "B", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T22:30:00Z", "payload": "another"},
        ]
        for protocol in ({}, {"protocol": "1"}):
            for batch in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, first=batch[0]["record_id"]):
                    self.assertEqual(self.request(batch, protocol), {
                        "protocol": "1", "accepted_count": 3, "duplicate_count": 2,
                    })

    def test_empty_and_single_receipt(self):
        receipt = {"record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
                   "occurred_at": "2026-04-01T10:00:00Z", "payload": "first"}
        for protocol in ({}, {"protocol": "1"}):
            for batch in ([], [receipt]):
                with self.subTest(protocol=protocol, size=len(batch)):
                    self.assertEqual(self.request(batch, protocol), {
                        "protocol": "1", "accepted_count": len(batch), "duplicate_count": 0,
                    })
