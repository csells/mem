import json
import subprocess
import sys
import unittest

def ask(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)

def receipt(record_id, delivery_id, occurred_at, account_id="A", payload=None):
    return {"record_id": record_id, "account_id": account_id,
            "delivery_id": delivery_id, "occurred_at": occurred_at,
            "payload": payload or ("payload:" + record_id)}

class Summary(unittest.TestCase):
    def test_omitted_protocol_selects_current(self):
        self.assertEqual(ask({"command": "summary", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0})

    def test_explicit_protocol_2_selects_same_agreement(self):
        got = ask({"command": "summary", "protocol": "2",
                   "receipts": [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="B")]})
        self.assertEqual(got, {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count"})

    def test_protocol_2_delivery_id_alone_identifies(self):
        # Under protocol 2 the same delivery_id under another account is
        # another receipt of that delivery, so only one is accepted.
        got = ask({"command": "summary", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
            receipt("R-3", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_2_latest_instant_wins_across_accounts(self):
        got = ask({"command": "summary", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
            receipt("R-3", "D-1", "2026-04-01T09:00:00Z", account_id="C"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_2_offset_crossing_date_boundary(self):
        # 2026-04-01T01:00:00+02:00 is 2026-03-31T23:00:00Z, the latest instant;
        # under protocol 2 it wins without leaving April 1 local.
        got = ask({"command": "summary", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00", account_id="A"),
            receipt("R-2", "D-1", "2026-03-31T23:00:00Z", account_id="A"),
            receipt("R-3", "D-1", "2026-04-01T01:00:00+02:00", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_2_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "summary", "protocol": "2", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00", account_id="B"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z", account_id="C"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_protocol_2_applies_regardless_of_receipt_dates(self):
        # The current protocol governs the whole set even when some receipts
        # predate the protocol 2 adoption.
        got = ask({"command": "summary", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2021-06-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_response_has_exactly_named_fields(self):
        got = ask({"command": "summary", "protocol": "1",
                   "receipts": [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="B")]})
        self.assertEqual(got, {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count"})

    def test_same_delivery_id_different_accounts_are_separate_deliveries(self):
        got = ask({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
            receipt("R-3", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 1))

    def test_duplicates_counted_per_account_in_cross_account_batch(self):
        got = ask({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="A"),
            receipt("R-3", "D-2", "2026-04-01T09:00:00Z", account_id="B"),
            receipt("R-4", "D-2", "2026-04-01T08:00:00Z", account_id="B"),
            receipt("R-5", "D-3", "2026-04-01T08:00:00Z", account_id="C"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (3, 2))

    def test_offset_crossing_date_boundary_across_accounts(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, earlier than both
        # same-day Z timestamps, so R-1 must win without leaving April 1 local.
        got = ask({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00", account_id="A"),
            receipt("R-2", "D-1", "2026-03-31T23:00:00Z", account_id="A"),
            receipt("R-3", "D-9", "2026-04-01T01:00:00+02:00", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 1))

    def test_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "summary", "protocol": "1", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00", account_id="B"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_unsupported_protocol_rejected(self):
        got = ask({"command": "summary", "protocol": "9", "receipts": []})
        self.assertEqual(got, {"error": "unsupported_protocol"})

    def test_count_behavior_preserved(self):
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z"),
        ]})
        self.assertEqual(got, {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

if __name__ == "__main__":
    unittest.main()
