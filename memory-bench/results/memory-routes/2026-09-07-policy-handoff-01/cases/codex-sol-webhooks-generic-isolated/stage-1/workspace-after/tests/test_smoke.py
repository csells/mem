import json
import subprocess
import sys
import unittest

class Smoke(unittest.TestCase):
    def test_ping(self):
        p = subprocess.run([sys.executable, "main.py"], input='{"command":"ping"}', text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p.stdout), {"status":"ok","product":"Courier Relay"})

    def test_count_uses_current_protocol_when_omitted(self):
        receipts = [
            {
                "record_id": "later",
                "account_id": "account",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-01T00:30:00+01:00",
                "payload": "later input, earlier instant",
            },
            {
                "record_id": "earlier-input",
                "account_id": "account",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-03-31T23:45:00Z",
                "payload": "duplicate",
            },
            {
                "record_id": "other-delivery",
                "account_id": "account",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-03-31T23:45:00Z",
                "payload": "accepted",
            },
        ]

        response = self.run_cli({"command": "count", "receipts": receipts})

        self.assertEqual(
            response,
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_count_breaks_equal_instant_ties_without_changing_counts(self):
        receipts = [
            {
                "record_id": "z-record",
                "account_id": "account",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T01:00:00+01:00",
                "payload": "duplicate",
            },
            {
                "record_id": "a-record",
                "account_id": "account",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "accepted by record id",
            },
        ]

        response = self.run_cli(
            {"command": "count", "protocol": "1", "receipts": receipts}
        )

        self.assertEqual(
            response,
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )

    def run_cli(self, request):
        process = subprocess.run(
            [sys.executable, "main.py"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(process.stdout)
