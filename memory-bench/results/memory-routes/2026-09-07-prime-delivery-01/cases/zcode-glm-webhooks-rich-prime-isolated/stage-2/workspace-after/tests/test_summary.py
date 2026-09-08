import json
import subprocess
import sys
import unittest

def relay(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)

def receipt(record_id, delivery_id, occurred_at="2026-04-01T10:00:00Z", account_id="A"):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": "payload:" + record_id,
    }

class Summary(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(relay({"command": "summary", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(relay({"command": "summary", "protocol": "1",
                                "receipts": [receipt("R-1", "D-1")]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(relay({"command": "summary", "receipts": [receipt("R-1", "D-1")]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_same_delivery_id_different_accounts_are_separate_deliveries(self):
        self.assertEqual(relay({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", account_id="A"),
            receipt("R-2", "D-1", account_id="B"),
            receipt("R-3", "D-1", account_id="C"),
        ]}), {"protocol": "1", "accepted_count": 3, "duplicate_count": 0})

    def test_duplicates_within_account_in_cross_account_batch(self):
        self.assertEqual(relay({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", account_id="A"),
            receipt("R-2", "D-1", account_id="A"),
            receipt("R-3", "D-2", account_id="B"),
            receipt("R-4", "D-1", account_id="B"),
        ]}), {"protocol": "1", "accepted_count": 3, "duplicate_count": 1})

    def test_cross_account_batch_mixed(self):
        self.assertEqual(relay({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="A"),
            receipt("R-3", "D-2", account_id="B"),
            receipt("R-4", "D-1", "2026-04-01T23:30:00-05:00", account_id="C"),
            receipt("R-5", "D-1", "2026-04-02T04:30:00Z", account_id="C"),
        ]}), {"protocol": "1", "accepted_count": 3, "duplicate_count": 2})
