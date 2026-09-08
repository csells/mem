import json
import subprocess
import sys
import unittest


def receipt(record_id, occurred_at, delivery_id="D-1", account_id="A", payload=None):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": payload if payload is not None else "payload:" + record_id,
    }


class SummaryEndToEnd(unittest.TestCase):
    def cli(self, request):
        proc = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                              text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)

    def test_empty(self):
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(self.cli({"command": "summary", "protocol": "1",
                                   "receipts": [receipt("R-1", "2026-04-01T10:00:00Z")]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(self.cli({"command": "summary",
                                   "receipts": [receipt("R-1", "2026-04-01T10:00:00Z")]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})

    def test_explicit_protocol_2_cross_account_identity(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "2", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})

    def test_explicit_protocol_1_keeps_account_scoped_identity(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})

    def test_protocol_2_latest_instant_with_equal_instant_tie(self):
        # Same delivery_id across accounts: 2026-04-01T23:00:00Z is later than
        # 2026-04-02T00:30:00+02:00 (22:30Z); the third shares the winner's
        # instant, so the smallest record_id wins the tie.
        receipts = [
            receipt("R-b", "2026-04-02T00:30:00+02:00", "D-1", account_id="A"),
            receipt("R-a", "2026-04-01T23:00:00Z", "D-1", account_id="B"),
            receipt("R-c", "2026-04-01T21:00:00-02:00", "D-1", account_id="C"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "2", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 2})

    def test_unsupported_protocol(self):
        self.assertEqual(self.cli({"command": "summary", "protocol": "9", "receipts": []}),
                         {"error": "unsupported_protocol"})

    def test_cross_account_same_delivery_id_counts_separately(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})

    def test_duplicates_within_account_across_offset_spellings(self):
        # 2026-03-31T23:00:00Z and 2026-04-01T01:00:00+02:00 are the same instant;
        # the smallest record_id wins the tie, so three receipts yield one duplicate.
        receipts = [
            receipt("R-b", "2026-03-31T23:00:00Z", "D-1", account_id="A"),
            receipt("R-a", "2026-04-01T01:00:00+02:00", "D-1", account_id="A"),
            receipt("R-c", "2026-04-01T09:00:00Z", "D-1", account_id="A"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 2})

    def test_mixed_accounts_and_deliveries(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T09:00:00Z", "D-1", account_id="A"),
            receipt("R-3", "2026-04-01T10:00:00Z", "D-1", account_id="B"),
            receipt("R-4", "2026-04-01T10:00:00Z", "D-2", account_id="B"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 3, "duplicate_count": 1})

    def test_offset_crossing_date_boundary_picks_earliest_instant(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, earlier than the
        # receipt whose local spelling is the prior date.
        receipts = [
            receipt("R-late", "2026-03-31T23:00:00Z", "D-1", account_id="A"),
            receipt("R-early", "2026-04-01T00:30:00+02:00", "D-1", account_id="A"),
        ]
        self.assertEqual(self.cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})
