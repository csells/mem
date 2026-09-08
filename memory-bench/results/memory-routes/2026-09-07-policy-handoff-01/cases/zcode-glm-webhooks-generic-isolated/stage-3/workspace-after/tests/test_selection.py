import unittest
import main

def receipt(record_id, occurred_at, delivery_id="D-1", account_id="A"):
    return {"record_id": record_id, "account_id": account_id,
            "delivery_id": delivery_id, "occurred_at": occurred_at,
            "payload": "payload:" + record_id}

class Protocol2Selection(unittest.TestCase):
    def test_latest_instant_wins(self):
        receipts = [
            receipt("R-1", "2026-04-01T09:00:00Z"),
            receipt("R-2", "2026-04-01T10:00:00Z"),
            receipt("R-3", "2026-04-01T08:00:00Z"),
        ]
        self.assertEqual(main.select_accepted_v2(receipts), [receipts[1]])

    def test_latest_compares_offsets_as_utc_instants(self):
        # 00:30+02:00 is 22:30Z on the prior calendar date, earlier than 23:00Z.
        receipts = [
            receipt("R-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "2026-03-31T23:00:00Z"),
        ]
        self.assertEqual(main.select_accepted_v2(receipts), [receipts[1]])

    def test_equal_instants_prefer_smallest_record_id(self):
        receipts = [
            receipt("R-2", "2026-04-01T10:00:00Z"),
            receipt("R-1", "2026-04-01T12:00:00+02:00"),  # same instant
        ]
        self.assertEqual(main.select_accepted_v2(receipts), [receipts[1]])

    def test_delivery_identity_spans_accounts(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", account_id="B"),
        ]
        self.assertEqual(main.select_accepted_v2(receipts), [receipts[1]])

    def test_accepted_receipts_keep_input_order_and_original_fields(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", delivery_id="D-2"),
            receipt("R-2", "2026-04-01T12:00:00+02:00", delivery_id="D-1"),  # 10:00Z, latest
            receipt("R-3", "2026-04-01T09:00:00Z", delivery_id="D-1"),
        ]
        accepted = main.select_accepted_v2(receipts)
        self.assertEqual(accepted, [receipts[0], receipts[1]])
        self.assertIs(accepted[1], receipts[1])  # original spelling and payload retained

class Protocol1Selection(unittest.TestCase):
    def test_earliest_instant_wins(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "2026-04-01T09:00:00Z"),
        ]
        self.assertEqual(main.select_accepted_v1(receipts), [receipts[1]])

    def test_identity_is_scoped_to_account(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", account_id="B"),
        ]
        self.assertEqual(main.select_accepted_v1(receipts), receipts)

if __name__ == "__main__":
    unittest.main()
