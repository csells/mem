import json
import subprocess
import sys
import unittest

import main


def receipt(record_id, occurred_at, delivery_id="D-1", account_id="A", payload=None):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": payload if payload is not None else "payload:" + record_id,
    }


class CountEndToEnd(unittest.TestCase):
    def cli(self, request):
        proc = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                              text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)

    def test_empty(self):
        self.assertEqual(self.cli({"command": "count", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(self.cli({"command": "count", "protocol": "1",
                                   "receipts": [receipt("R-1", "2026-04-01T10:00:00Z")]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(self.cli({"command": "count",
                                   "receipts": [receipt("R-1", "2026-04-01T10:00:00Z")]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})

    def test_explicit_protocol_2_matches_omitted(self):
        receipts = [receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
                    receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B")]
        self.assertEqual(self.cli({"command": "count", "protocol": "2", "receipts": receipts}),
                         self.cli({"command": "count", "receipts": receipts}))

    def test_duplicates_and_distinct_deliveries(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1"),
            receipt("R-3", "2026-04-01T11:00:00Z", "D-1"),
            receipt("R-4", "2026-04-01T09:00:00Z", "D-2"),
        ]
        self.assertEqual(self.cli({"command": "count", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 2})

    def test_ping_preserved(self):
        self.assertEqual(self.cli({"command": "ping"}),
                         {"status": "ok", "product": "Courier Relay"})

    def test_unknown_command_preserved(self):
        self.assertEqual(self.cli({"command": "frobnicate"}), {"error": "unknown_command"})


class Protocol1Acceptance(unittest.TestCase):
    def accepted_ids(self, receipts):
        return [r["record_id"] for r in main.protocol1_accepted(receipts)]

    def test_earliest_instant_wins_regardless_of_offset_spelling(self):
        # 00:30+02:00 is 2026-03-31T22:30:00Z, earlier than 23:00Z despite the later local date.
        receipts = [
            receipt("R-late", "2026-03-31T23:00:00Z"),
            receipt("R-early", "2026-04-01T00:30:00+02:00"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-early"])

    def test_equal_instants_break_tie_by_smallest_record_id(self):
        receipts = [
            receipt("R-b", "2026-04-01T14:00:00+02:00"),
            receipt("R-a", "2026-04-01T12:00:00Z"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-a"])

    def test_same_delivery_id_under_different_accounts_is_separate(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-1", "R-2"])

    def test_accepted_keeps_original_input_order(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-2"),
            receipt("R-2", "2026-04-01T09:00:00Z", "D-1"),
            receipt("R-3", "2026-04-01T08:00:00Z", "D-1"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-1", "R-3"])


class Protocol2Acceptance(unittest.TestCase):
    def accepted_ids(self, receipts):
        return [r["record_id"] for r in main.protocol2_accepted(receipts)]

    def test_same_delivery_id_under_different_accounts_is_one_identity(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-2"])

    def test_latest_instant_wins_regardless_of_offset_spelling(self):
        # 00:30+02:00 is 2026-04-01T22:30:00Z, earlier than 23:00Z despite the later local date.
        receipts = [
            receipt("R-early", "2026-04-02T00:30:00+02:00"),
            receipt("R-late", "2026-04-01T23:00:00Z"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-late"])

    def test_latest_instant_across_widely_separated_dates(self):
        # The identity spans the entire supplied set regardless of receipt dates.
        receipts = [
            receipt("R-old", "2020-01-01T00:00:00Z"),
            receipt("R-new", "2099-12-31T23:59:59Z"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-new"])

    def test_equal_instants_break_tie_by_smallest_record_id(self):
        receipts = [
            receipt("R-b", "2026-04-01T14:00:00+02:00"),
            receipt("R-a", "2026-04-01T12:00:00Z"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-a"])

    def test_accepted_keeps_original_input_order(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-2"),
            receipt("R-2", "2026-04-01T09:00:00Z", "D-1"),
            receipt("R-3", "2026-04-01T08:00:00Z", "D-1"),
        ]
        self.assertEqual(self.accepted_ids(receipts), ["R-1", "R-2"])

    def test_accepted_receipt_retains_original_fields_and_spelling(self):
        # 01:30+02:00 is 2026-03-31T23:30:00Z, later than 23:00Z, so R-keep wins.
        original = receipt("R-keep", "2026-04-01T01:30:00+02:00", "D-1", account_id="A",
                           payload="body text")
        receipts = [receipt("R-drop", "2026-03-31T23:00:00Z"), original]
        accepted = main.protocol2_accepted(receipts)
        self.assertEqual(len(accepted), 1)
        self.assertIs(accepted[0], original)
