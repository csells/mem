import json
import subprocess
import sys
import unittest


class Count(unittest.TestCase):
    def request(self, request):
        result = subprocess.run(
            [sys.executable, "main.py"], input=json.dumps(request),
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def test_empty_default_protocol(self):
        self.assertEqual(self.request({"command": "count", "receipts": []}), {
            "protocol": "1", "accepted_count": 0, "duplicate_count": 0,
        })

    def test_duplicate_delivery_with_different_receipt_contents(self):
        receipts = [
            {"record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-02T00:30:00+02:00", "payload": "first"},
            {"record_id": "R-2", "account_id": "A", "delivery_id": "D-2",
             "occurred_at": "2026-04-01T22:30:00Z", "payload": "first"},
            {"record_id": "R-3", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T21:00:00Z", "payload": "changed"},
            {"record_id": "R-4", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T21:00:00Z", "payload": "another"},
        ]
        for protocol in ({}, {"protocol": "1"}):
            with self.subTest(protocol=protocol):
                self.assertEqual(self.request({
                    "command": "count", "receipts": receipts, **protocol,
                }), {"protocol": "1", "accepted_count": 2, "duplicate_count": 2})

    def test_unknown_command(self):
        self.assertEqual(self.request({"command": "missing"}), {
            "error": "unknown_command",
        })
