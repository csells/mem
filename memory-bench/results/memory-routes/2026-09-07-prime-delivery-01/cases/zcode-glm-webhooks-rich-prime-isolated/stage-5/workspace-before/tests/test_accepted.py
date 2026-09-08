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

class Accepted(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(relay({"command": "accepted", "protocol": "2", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0,
                          "receipts": []})

    def test_single_receipt_returned_unchanged(self):
        only = receipt("R-1", "D-1")
        self.assertEqual(relay({"command": "accepted", "protocol": "2",
                                "receipts": [only]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [only]})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(relay({"command": "accepted",
                                "receipts": [receipt("R-1", "D-1")]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [receipt("R-1", "D-1")]})

    def test_protocol_2_latest_instant_wins_within_account(self):
        self.assertEqual(relay({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
        ]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1,
                          "receipts": [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]})

    def test_protocol_2_same_delivery_id_across_accounts_one_delivery(self):
        self.assertEqual(relay({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
        ]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1,
                          "receipts": [receipt("R-2", "D-1", "2026-04-01T11:00:00Z",
                                               account_id="B")]})

    def test_protocol_2_equal_instants_use_smallest_record_id(self):
        early_id = receipt("R-1", "D-1", "2026-04-02T04:30:00Z", account_id="A")
        late_id = receipt("R-2", "D-1", "2026-04-01T23:30:00-05:00", account_id="B")
        self.assertEqual(relay({"command": "accepted", "protocol": "2",
                                "receipts": [late_id, early_id]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1,
                          "receipts": [early_id]})

    def test_original_input_order_and_spelling_retained(self):
        winner = receipt("R-1", "D-1", "2026-04-01T23:30:00-05:00", account_id="A")
        duplicate = receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B")
        other = receipt("R-3", "D-2", "2027-01-01T00:00:00Z", account_id="C")
        self.assertEqual(relay({"command": "accepted", "protocol": "2",
                                "receipts": [winner, duplicate, other]}),
                         {"protocol": "2", "accepted_count": 2, "duplicate_count": 1,
                          "receipts": [winner, other]})

    def test_counts_equal_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="A"),
            receipt("R-3", "D-2", account_id="B"),
            receipt("R-4", "D-1", "2026-04-01T23:30:00-05:00", account_id="C"),
            receipt("R-5", "D-1", "2026-04-02T04:30:00Z", account_id="C"),
        ]
        summary = relay({"command": "summary", "receipts": receipts})
        accepted = relay({"command": "accepted", "receipts": receipts})
        self.assertEqual({k: accepted[k] for k in summary}, summary)

    def test_response_contains_exactly_named_fields(self):
        got = relay({"command": "accepted", "receipts": [receipt("R-1", "D-1")]})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count",
                                    "receipts"})

    def test_protocol_1_earliest_instant_wins(self):
        self.assertEqual(relay({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
        ]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 1,
                          "receipts": [receipt("R-2", "D-1", "2026-04-01T09:00:00Z")]})
