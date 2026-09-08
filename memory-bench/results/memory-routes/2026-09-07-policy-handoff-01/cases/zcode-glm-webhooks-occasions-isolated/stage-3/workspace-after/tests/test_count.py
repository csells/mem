import json
import subprocess
import sys
import unittest

def ask(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)

def receipt(record_id, account_id, delivery_id, occurred_at):
    return {"record_id": record_id, "account_id": account_id,
            "delivery_id": delivery_id, "occurred_at": occurred_at,
            "payload": "payload:" + record_id}

class Count(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "count", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(
            ask({"command": "count", "protocol": "1",
                 "receipts": [receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z")]}),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_single_protocol_2(self):
        self.assertEqual(
            ask({"command": "count", "protocol": "2",
                 "receipts": [receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z")]}),
            {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(ask({"command": "count", "receipts": []})["protocol"], "2")

    def test_unsupported_protocol(self):
        self.assertEqual(ask({"command": "count", "protocol": "9", "receipts": []}),
                         {"error": "unsupported_protocol"})

    def test_duplicates_same_identity(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "A", "D-1", "2026-04-01T09:00:00Z"),
            receipt("R-3", "A", "D-1", "2026-04-01T11:00:00Z"),
        ]
        self.assertEqual(ask({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 2})

    def test_same_delivery_id_different_accounts_are_separate_protocol_1(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T10:00:00Z"),
        ]
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})

    def test_same_delivery_id_different_accounts_share_identity(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T10:00:00Z"),
        ]
        self.assertEqual(ask({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})

    def test_offsets_compared_as_utc_instants(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, earlier than 23:00Z
        # even though its local date is later.
        receipts = [
            receipt("R-1", "A", "D-1", "2026-03-31T23:00:00Z"),
            receipt("R-2", "A", "D-1", "2026-04-01T00:30:00+02:00"),
        ]
        self.assertEqual(ask({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})

    def test_equal_instants_tie_break_does_not_change_counts(self):
        # Same instant spelled two ways: still one delivery, one duplicate.
        receipts = [
            receipt("R-2", "A", "D-1", "2026-04-01T12:00:00Z"),
            receipt("R-1", "A", "D-1", "2026-04-01T14:00:00+02:00"),
        ]
        self.assertEqual(ask({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})

    def test_multiple_deliveries(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "A", "D-2", "2026-04-01T10:00:00Z"),
            receipt("R-3", "A", "D-1", "2026-04-01T09:00:00Z"),
            receipt("R-4", "A", "D-3", "2026-04-01T10:00:00-05:00"),
        ]
        self.assertEqual(ask({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 3, "duplicate_count": 1})

    def test_cross_account_duplicates_merge_protocol_2(self):
        # D-1 arrives in two accounts; protocol 2 sees one delivery, so the
        # later 11:00Z receipt makes the 10:00Z one a duplicate.
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T11:00:00Z"),
            receipt("R-3", "A", "D-2", "2026-04-01T09:00:00Z"),
            receipt("R-4", "B", "D-2", "2026-04-01T08:00:00Z"),
        ]
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 2, "duplicate_count": 2})

class Preserved(unittest.TestCase):
    def test_ping(self):
        self.assertEqual(ask({"command": "ping"}),
                         {"status": "ok", "product": "Courier Relay"})

    def test_unknown_command(self):
        self.assertEqual(ask({"command": "frobnicate"}), {"error": "unknown_command"})
