import json
import subprocess
import sys
import unittest

class Smoke(unittest.TestCase):
    def test_ping(self):
        p = subprocess.run([sys.executable, "main.py"], input='{"command":"ping"}', text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p.stdout), {"status":"ok","product":"Courier Relay"})

    def test_accepted_protocol_1_uses_delivery_identity_and_earliest_receipt(self):
        receipts = [
            {"record_id": "late", "account_id": "A", "delivery_id": "D", "occurred_at": "2026-01-02T00:00:00Z", "payload": "late"},
            {"record_id": "early", "account_id": "B", "delivery_id": "D", "occurred_at": "2026-01-01T19:00:00-05:00", "payload": "early"},
            {"record_id": "tie-z", "account_id": "C", "delivery_id": "E", "occurred_at": "2026-01-03T00:00:00Z", "payload": "tie-z"},
            {"record_id": "tie-a", "account_id": "D", "delivery_id": "E", "occurred_at": "2026-01-02T19:00:00-05:00", "payload": "tie-a"},
        ]
        request = json.dumps({"command": "accepted", "protocol": "1", "receipts": receipts})
        p = subprocess.run([sys.executable, "main.py"], input=request, text=True, capture_output=True, check=True)

        result = json.loads(p.stdout)
        self.assertEqual(result["protocol"], "1")
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["duplicate_count"], 2)
        self.assertEqual([receipt["record_id"] for receipt in result["receipts"]], ["early", "tie-a"])
        self.assertEqual(result["receipts"][0], receipts[1])
        self.assertEqual(result["receipts"][1], receipts[3])
