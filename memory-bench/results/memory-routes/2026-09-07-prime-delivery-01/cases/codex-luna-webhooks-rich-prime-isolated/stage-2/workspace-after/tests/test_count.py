import unittest

from main import run


def receipt(record_id, account_id, delivery_id, occurred_at):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": "payload:" + record_id,
    }


class CountReceipts(unittest.TestCase):
    def test_empty_and_omitted_protocol(self):
        self.assertEqual(
            run({"command": "count", "receipts": []}),
            {"protocol": "1", "accepted_count": 0, "duplicate_count": 0},
        )

    def test_delivery_id_is_global_and_each_delivery_has_one_acceptance(self):
        receipts = [
            receipt("late", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("other", "A", "D-2", "2026-04-01T10:00:00Z"),
            receipt("early", "B", "D-1", "2026-04-01T09:00:00-02:00"),
        ]
        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_equal_utc_instants_use_smallest_record_id(self):
        receipts = [
            receipt("z", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("a", "A", "D-1", "2026-04-01T12:00:00+02:00"),
        ]
        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )


if __name__ == "__main__":
    unittest.main()
