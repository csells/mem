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

    def test_duplicates_and_distinct_deliveries(self):
        receipts = [
            {"record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-02T00:30:00+02:00", "payload": "first"},
            {"record_id": "R-2", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T22:00:00Z", "payload": "changed"},
            {"record_id": "R-3", "account_id": "A", "delivery_id": "D-2",
             "occurred_at": "2026-04-01T22:00:00Z", "payload": "first"},
            {"record_id": "R-4", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T22:00:00Z", "payload": "first"},
        ]
        for protocol in (None, "1"):
            for ordered in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, first=ordered[0]["record_id"]):
                    request = {"command": "count", "receipts": ordered}
                    if protocol is not None:
                        request["protocol"] = protocol
                    self.assertEqual(self.request(request), {
                        "protocol": "1", "accepted_count": 2, "duplicate_count": 2,
                    })

    def test_empty_current_protocol(self):
        self.assertEqual(self.request({"command": "count", "receipts": []}), {
            "protocol": "1", "accepted_count": 0, "duplicate_count": 0,
        })

    def test_unknown_command(self):
        self.assertEqual(self.request({"command": "unknown"}), {
            "error": "unknown_command",
        })
