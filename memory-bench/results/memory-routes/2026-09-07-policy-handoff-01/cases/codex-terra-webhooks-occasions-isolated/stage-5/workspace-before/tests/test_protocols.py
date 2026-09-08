import unittest

from main import run, select_receipts


def receipt(record_id, account_id, delivery_id, occurred_at):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": f"payload:{record_id}",
    }


class Protocols(unittest.TestCase):
    def test_default_protocol_2_uses_account_and_latest_utc_instant(self):
        receipts = [
            receipt("R-old", "A", "D", "2026-04-01T23:30:00-01:00"),
            receipt("R-new", "A", "D", "2026-04-02T00:00:00Z"),
            receipt("R-other-account", "B", "D", "2026-04-01T00:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "count", "receipts": receipts}),
            {"protocol": "2", "accepted_count": 2, "duplicate_count": 1},
        )
        self.assertEqual(select_receipts(receipts, "2"), {"R-old", "R-other-account"})

    def test_protocol_2_breaks_equal_instants_by_smallest_record_id(self):
        receipts = [
            receipt("z", "A", "D", "2026-04-01T12:00:00Z"),
            receipt("a", "A", "D", "2026-04-01T04:00:00-08:00"),
        ]

        self.assertEqual(
            run({"command": "summary", "protocol": "2", "receipts": receipts}),
            {"protocol": "2", "accepted_count": 1, "duplicate_count": 1},
        )
        self.assertEqual(select_receipts(receipts, "2"), {"a"})

    def test_protocol_1_remains_delivery_only_and_selects_earliest(self):
        receipts = [
            receipt("R-late", "A", "D", "2026-04-02T00:00:00Z"),
            receipt("R-early", "B", "D", "2026-04-01T00:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )
        self.assertEqual(select_receipts(receipts, "1"), {"R-early"})

    def test_accepted_returns_protocol_2_representatives_in_input_order(self):
        receipts = [
            receipt("late", "A", "D", "2026-04-02T00:00:00Z"),
            receipt("earlier", "A", "D", "2026-04-01T23:00:00Z"),
            receipt("other", "B", "D", "2026-04-01T00:00:00Z"),
            receipt("a", "C", "E", "2026-04-01T04:00:00-08:00"),
            receipt("z", "C", "E", "2026-04-01T12:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "accepted", "receipts": receipts}),
            {
                "protocol": "2",
                "accepted_count": 3,
                "duplicate_count": 2,
                "receipts": [receipts[0], receipts[2], receipts[3]],
            },
        )

    def test_accepted_empty_batch(self):
        self.assertEqual(
            run({"command": "accepted", "protocol": "2", "receipts": []}),
            {
                "protocol": "2",
                "accepted_count": 0,
                "duplicate_count": 0,
                "receipts": [],
            },
        )
