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

class Accepted(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "accepted", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0,
                          "duplicate_count": 0, "receipts": []})

    def test_single_returned_unchanged(self):
        only = receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z")
        self.assertEqual(ask({"command": "accepted", "protocol": "2",
                              "receipts": [only]}),
                         {"protocol": "2", "accepted_count": 1,
                          "duplicate_count": 0, "receipts": [only]})

    def test_latest_instant_wins_protocol_2(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "A", "D-1", "2026-04-01T09:00:00Z"),
        ]
        self.assertEqual(ask({"command": "accepted", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1,
                          "duplicate_count": 1,
                          "receipts": [receipts[0]]})

    def test_same_delivery_id_different_accounts_share_identity(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T10:30:00Z"),
        ]
        self.assertEqual(ask({"command": "accepted", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1,
                          "duplicate_count": 1,
                          "receipts": [receipts[1]]})

    def test_same_delivery_id_different_accounts_separate_protocol_1(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T10:30:00Z"),
        ]
        self.assertEqual(ask({"command": "accepted", "protocol": "1",
                              "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2,
                          "duplicate_count": 0, "receipts": receipts})

    def test_earliest_instant_wins_protocol_1(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "A", "D-1", "2026-04-01T09:00:00Z"),
        ]
        self.assertEqual(ask({"command": "accepted", "protocol": "1",
                              "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 1,
                          "duplicate_count": 1,
                          "receipts": [receipts[1]]})

    def test_equal_instants_use_smallest_record_id(self):
        # Same instant spelled two ways; R-1 wins the tie and keeps its
        # original +02:00 spelling in the output.
        receipts = [
            receipt("R-2", "A", "D-1", "2026-04-01T12:00:00Z"),
            receipt("R-1", "A", "D-1", "2026-04-01T14:00:00+02:00"),
        ]
        self.assertEqual(ask({"command": "accepted", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1,
                          "duplicate_count": 1,
                          "receipts": [receipts[1]]})

    def test_offsets_compared_as_utc_instants(self):
        # 2026-04-01T00:30:00+02:00 is 2026-03-31T22:30:00Z, earlier than
        # 23:00Z even though its local date is later.
        receipts = [
            receipt("R-1", "A", "D-1", "2026-03-31T23:00:00Z"),
            receipt("R-2", "A", "D-1", "2026-04-01T00:30:00+02:00"),
        ]
        self.assertEqual(ask({"command": "accepted", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1,
                          "duplicate_count": 1,
                          "receipts": [receipts[0]]})

    def test_original_input_order_preserved(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-2", "2026-04-01T08:00:00Z"),
            receipt("R-3", "A", "D-1", "2026-04-01T09:00:00Z"),
            receipt("R-4", "B", "D-2", "2026-04-01T11:00:00Z"),
        ]
        self.assertEqual(
            ask({"command": "accepted", "receipts": receipts})["receipts"],
            [receipts[0], receipts[3]])

    def test_counts_match_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "B", "D-1", "2026-04-01T10:30:00Z"),
            receipt("R-3", "C", "D-2", "2026-04-01T09:00:00Z"),
            receipt("R-4", "C", "D-2", "2026-04-01T09:00:00Z"),
        ]
        accepted = ask({"command": "accepted", "receipts": receipts})
        summary = ask({"command": "summary", "receipts": receipts})
        self.assertEqual(
            {k: accepted[k] for k in ("protocol", "accepted_count", "duplicate_count")},
            summary)

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(ask({"command": "accepted", "receipts": []})["protocol"], "2")

    def test_unsupported_protocol(self):
        self.assertEqual(ask({"command": "accepted", "protocol": "9", "receipts": []}),
                         {"error": "unsupported_protocol"})

if __name__ == "__main__":
    unittest.main()
