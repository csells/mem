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

class Accepted(unittest.TestCase):
    def test_omitted_protocol_selects_current(self):
        self.assertEqual(ask({"command": "accepted", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0,
                          "duplicate_count": 0, "receipts": []})

    def test_empty_set_returns_empty_receipts_and_zero_counts(self):
        got = ask({"command": "accepted", "protocol": "2", "receipts": []})
        self.assertEqual(got, {"protocol": "2", "accepted_count": 0,
                               "duplicate_count": 0, "receipts": []})
        self.assertEqual(set(got), {"protocol", "accepted_count",
                                    "duplicate_count", "receipts"})

    def test_single_receipt_returned_unchanged(self):
        single = receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="B")
        got = ask({"command": "accepted", "protocol": "2", "receipts": [single]})
        self.assertEqual(got["receipts"], [single])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 0))

    def test_protocol_2_delivery_id_alone_identifies(self):
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B"),
            receipt("R-3", "D-2", "2026-04-01T10:00:00Z", account_id="C"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1", "R-3"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 1))

    def test_latest_instant_representative_returned(self):
        winner = receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B")
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            winner,
            receipt("R-3", "D-1", "2026-04-01T09:00:00Z", account_id="C"),
        ]})
        self.assertEqual(got["receipts"], [winner])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_offset_crossing_date_boundary(self):
        # 2026-04-01T01:00:00+02:00 is 2026-03-31T23:00:00Z, the latest instant;
        # it wins without leaving April 1 local and keeps its offset spelling.
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "D-1", "2026-03-31T22:45:00Z"),
            receipt("R-3", "D-1", "2026-04-01T01:00:00+02:00"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-3"])
        self.assertEqual(got["receipts"][0]["occurred_at"], "2026-04-01T01:00:00+02:00")

    def test_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00", account_id="B"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z", account_id="C"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_original_input_order_preserved(self):
        # D-2's representative appears first because it was first in input,
        # even though D-1's representative has the smaller record_id.
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-5", "D-2", "2026-04-01T10:00:00Z"),
            receipt("R-1", "D-1", "2026-04-01T09:00:00Z"),
            receipt("R-6", "D-2", "2026-04-01T08:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-5", "R-2"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 2))

    def test_payload_preserved_unchanged(self):
        got = ask({"command": "accepted", "protocol": "2", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", payload="special:payload"),
        ]})
        self.assertEqual(got["receipts"][0]["payload"], "special:payload")

    def test_counts_equal_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
            receipt("R-3", "D-2", "2026-03-31T23:00:00-05:00", account_id="C"),
        ]
        accepted = ask({"command": "accepted", "protocol": "2", "receipts": receipts})
        summary = ask({"command": "summary", "protocol": "2", "receipts": receipts})
        self.assertEqual((accepted["accepted_count"], accepted["duplicate_count"]),
                         (summary["accepted_count"], summary["duplicate_count"]))

    def test_protocol_1_empty_set_returns_empty_receipts_and_zero_counts(self):
        got = ask({"command": "accepted", "protocol": "1", "receipts": []})
        self.assertEqual(got, {"protocol": "1", "accepted_count": 0,
                               "duplicate_count": 0, "receipts": []})
        self.assertEqual(set(got), {"protocol", "accepted_count",
                                    "duplicate_count", "receipts"})

    def test_protocol_1_single_receipt_returned_unchanged(self):
        single = receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="B")
        got = ask({"command": "accepted", "protocol": "1", "receipts": [single]})
        self.assertEqual(got["receipts"], [single])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 0))

    def test_protocol_1_pair_identity_separates_accounts(self):
        # The same delivery_id under different accounts is a separate delivery,
        # so both receipts are accepted.
        got = ask({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1", "R-2"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 0))

    def test_protocol_1_earliest_instant_representative_returned(self):
        winner = receipt("R-3", "D-1", "2026-04-01T09:00:00Z")
        got = ask({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T11:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
            winner,
        ]})
        self.assertEqual(got["receipts"], [winner])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 2))

    def test_protocol_1_offset_crossing_date_boundary(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, the earliest
        # instant; it wins without leaving April 1 local and keeps its spelling.
        got = ask({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "D-1", "2026-03-31T22:45:00Z"),
            receipt("R-3", "D-1", "2026-04-01T01:00:00+02:00"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1"])
        self.assertEqual(got["receipts"][0]["occurred_at"], "2026-04-01T00:30:00+02:00")

    def test_protocol_1_equal_instants_tie_break_by_record_id(self):
        got = ask({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00"),
            receipt("R-1", "D-1", "2026-04-01T12:00:00Z"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (1, 1))

    def test_protocol_1_original_input_order_preserved(self):
        # R-6 appears first because it was first in input among the winners,
        # even though R-2 has the smaller record_id.
        got = ask({"command": "accepted", "protocol": "1", "receipts": [
            receipt("R-5", "D-2", "2026-04-01T10:00:00Z"),
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-6", "D-2", "2026-04-01T08:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
        ]})
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-6", "R-2"])
        self.assertEqual((got["accepted_count"], got["duplicate_count"]), (2, 2))

    def test_protocol_1_counts_equal_count_and_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="A"),
            receipt("R-3", "D-2", "2026-03-31T23:00:00-05:00", account_id="C"),
        ]
        accepted = ask({"command": "accepted", "protocol": "1", "receipts": receipts})
        count = ask({"command": "count", "protocol": "1", "receipts": receipts})
        summary = ask({"command": "summary", "protocol": "1", "receipts": receipts})
        self.assertEqual((accepted["accepted_count"], accepted["duplicate_count"]),
                         (count["accepted_count"], count["duplicate_count"]))
        self.assertEqual((accepted["accepted_count"], accepted["duplicate_count"]),
                         (summary["accepted_count"], summary["duplicate_count"]))

    def test_unsupported_protocol_rejected(self):
        self.assertEqual(ask({"command": "accepted", "protocol": "9", "receipts": []}),
                         {"error": "unsupported_protocol"})

    def test_count_and_summary_versions_remain_supported(self):
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z"),
        ]}), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})
        self.assertEqual(ask({"command": "summary", "protocol": "2", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0})

if __name__ == "__main__":
    unittest.main()
