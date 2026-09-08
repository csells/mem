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

class Count(unittest.TestCase):
    def test_omitted_protocol_selects_current(self):
        self.assertEqual(ask({"command": "count", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0})

    def test_explicit_protocol_2_selects_same_agreement(self):
        got = ask({"command": "count", "protocol": "2",
                   "receipts": [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]})
        self.assertEqual(got, {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count"})

    def test_protocol_2_delivery_id_alone_identifies(self):
        # Under protocol 2 the same delivery_id under another account is
        # another receipt of that delivery, not a separate delivery.
        got = ask({"command": "count", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_protocol_2_latest_instant_wins(self):
        got = ask({"command": "count", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z"),
            receipt("R-3", "D-1", "2026-04-01T09:00:00Z"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_2_offset_crossing_date_boundary(self):
        # 2026-04-01T01:00:00+02:00 is 2026-03-31T23:00:00Z, the latest instant;
        # under protocol 2 it wins without leaving April 1 local.
        got = ask({"command": "count", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "D-1", "2026-03-31T23:00:00Z"),
            receipt("R-3", "D-1", "2026-04-01T01:00:00+02:00"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_2_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "count", "protocol": "2", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_protocol_2_applies_regardless_of_receipt_dates(self):
        # The current protocol governs the whole set even when some receipts
        # predate the protocol 2 adoption.
        got = ask({"command": "count", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2021-06-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
            receipt("R-3", "D-2", "2020-01-02T00:00:00Z", account_id="C"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 1))

    def test_response_has_exactly_named_fields(self):
        got = ask({"command": "count", "protocol": "1",
                   "receipts": [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]})
        self.assertEqual(got, {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count"})

    def test_duplicates_for_same_delivery_identity(self):
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z"),
            receipt("R-3", "D-1", "2026-04-01T09:00:00Z"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_offset_crossing_date_boundary(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, earlier than both
        # same-day Z timestamps, so R-1 must win without leaving April 1 local.
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "D-1", "2026-03-31T23:00:00Z"),
            receipt("R-3", "D-1", "2026-04-01T01:00:00+02:00"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_record_id_order_is_code_point(self):
        # "Z" (U+005A) sorts before "a" (U+0061) and before "é" (U+00E9).
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("a", "D-1", "2026-04-01T10:00:00Z"),
            receipt("Z", "D-1", "2026-04-01T10:00:00Z"),
            receipt("é", "D-1", "2026-04-01T10:00:00Z"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_same_delivery_id_different_accounts(self):
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 0))

    def test_multiple_deliveries_counted_independently(self):
        got = ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-3", "D-2", "2026-04-01T10:00:00Z"),
            receipt("R-4", "D-2", "2026-04-02T10:00:00Z"),
            receipt("R-5", "D-3", "2026-01-31T23:59:59-05:00"),
        ]})
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (3, 2))

    def test_ping_and_unknown_command_preserved(self):
        self.assertEqual(ask({"command": "ping"}),
                         {"status": "ok", "product": "Courier Relay"})
        self.assertEqual(ask({"command": "wat"}), {"error": "unknown_command"})

if __name__ == "__main__":
    unittest.main()
