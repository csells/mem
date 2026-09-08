import json
import subprocess
import sys
import unittest


class Count(unittest.TestCase):
    def request(self, request):
        result = subprocess.run(
            [sys.executable, "main.py"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_delivery_identity_counts(self):
        receipts = [
            {
                "record_id": record_id,
                "account_id": "A",
                "delivery_id": delivery_id,
                "occurred_at": occurred_at,
                "payload": payload,
            }
            for record_id, delivery_id, occurred_at, payload in [
                ("R-3", "D-1", "2026-04-01T00:00:00Z", "first"),
                ("R-2", "D-2", "2026-04-01T00:00:00Z", "first"),
                ("R-1", "D-1", "2026-04-01T01:00:00+02:00", "changed"),
                ("R-0", "D-1", "2026-03-31T23:00:00Z", "tie"),
            ]
        ]
        for protocol in ({}, {"protocol": "1"}):
            for ordered in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, order=ordered):
                    self.assertEqual(
                        self.request({"command": "count", "receipts": ordered, **protocol}),
                        {"protocol": "1", "accepted_count": 2, "duplicate_count": 2},
                    )

    def test_empty_default_protocol(self):
        self.assertEqual(
            self.request({"command": "count", "receipts": []}),
            {"protocol": "1", "accepted_count": 0, "duplicate_count": 0},
        )

    def test_unknown_command(self):
        self.assertEqual(
            self.request({"command": "missing"}), {"error": "unknown_command"}
        )
