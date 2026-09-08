import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

def receipt(record_id, delivery_id, occurred_at="2026-04-01T10:00:00Z", account_id="A"):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": "payload:" + record_id,
    }

class Protocol1Selection(unittest.TestCase):
    def test_earliest_instant_accepted(self):
        got = main.accepted_receipts("1", [
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
            receipt("R-1", "D-1", "2026-04-01T09:00:00Z"),
        ])
        self.assertEqual([r["record_id"] for r in got], ["R-1"])

    def test_equal_instants_use_smallest_record_id(self):
        got = main.accepted_receipts("1", [
            receipt("R-2", "D-1"),
            receipt("R-1", "D-1"),
        ])
        self.assertEqual([r["record_id"] for r in got], ["R-1"])

class Protocol2Selection(unittest.TestCase):
    def test_latest_instant_accepted(self):
        got = main.accepted_receipts("2", [
            receipt("R-1", "D-1", "2026-04-01T09:00:00Z"),
            receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
        ])
        self.assertEqual([r["record_id"] for r in got], ["R-2"])

    def test_latest_instant_across_accounts(self):
        got = main.accepted_receipts("2", [
            receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
        ])
        self.assertEqual([r["record_id"] for r in got], ["R-2"])

    def test_equal_instant_with_offset_crossing_date_boundary_uses_record_id(self):
        got = main.accepted_receipts("2", [
            receipt("R-2", "D-1", "2026-04-01T23:30:00-05:00"),
            receipt("R-1", "D-1", "2026-04-02T04:30:00Z"),
        ])
        self.assertEqual([r["record_id"] for r in got], ["R-1"])

    def test_original_input_order_and_spelling_retained(self):
        winner = receipt("R-1", "D-1", "2026-04-01T23:30:00-05:00", account_id="A")
        other = receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B")
        later = receipt("R-3", "D-2", "2027-01-01T00:00:00Z", account_id="C")
        got = main.accepted_receipts("2", [winner, other, later])
        self.assertEqual(got, [winner, later])

if __name__ == "__main__":
    unittest.main()
