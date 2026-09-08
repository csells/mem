import unittest

from main import accepted_receipts, run


def receipt(record_id, account_id, delivery_id):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": "2026-04-01T10:00:00Z",
        "payload": f"payload:{record_id}",
    }


class Summary(unittest.TestCase):
    def test_omitted_protocol_uses_current_protocol(self):
        self.assertEqual(
            run({"command": "summary", "receipts": []}),
            {"protocol": "2", "accepted_count": 0, "duplicate_count": 0},
        )

    def test_delivery_identity_includes_account(self):
        receipts = [
            receipt("a-first", "A", "shared"),
            receipt("a-duplicate", "A", "shared"),
            receipt("b-first", "B", "shared"),
            receipt("b-other", "B", "other"),
        ]

        self.assertEqual(
            run({"command": "summary", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 3, "duplicate_count": 1},
        )

    def test_count_remains_supported(self):
        receipts = [
            receipt("first", "A", "delivery"),
            receipt("duplicate", "A", "delivery"),
        ]

        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )

    def test_protocol_2_uses_delivery_id_across_accounts(self):
        receipts = [
            receipt("a-first", "A", "shared"),
            receipt("b-duplicate", "B", "shared"),
            receipt("b-other", "B", "other"),
        ]

        self.assertEqual(
            run({"command": "summary", "protocol": "2", "receipts": receipts}),
            {"protocol": "2", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_protocol_2_accepts_latest_instant_then_smallest_record_id(self):
        receipts = [
            {
                **receipt("middle", "A", "shared"),
                "occurred_at": "2026-04-01T09:30:00Z",
            },
            {
                **receipt("z-latest", "B", "shared"),
                "occurred_at": "2026-04-01T12:00:00+02:00",
            },
            {
                **receipt("a-latest", "C", "shared"),
                "occurred_at": "2026-04-01T05:00:00-05:00",
            },
            receipt("other", "A", "other"),
        ]

        self.assertEqual(
            accepted_receipts(receipts, "2"),
            [receipts[2], receipts[3]],
        )

    def test_protocol_1_still_accepts_earliest_per_account_delivery(self):
        receipts = [
            {
                **receipt("later", "A", "shared"),
                "occurred_at": "2026-04-01T00:30:00-01:00",
            },
            {
                **receipt("earlier", "A", "shared"),
                "occurred_at": "2026-04-01T01:00:00Z",
            },
            receipt("other-account", "B", "shared"),
        ]

        self.assertEqual(
            accepted_receipts(receipts, "1"),
            [receipts[1], receipts[2]],
        )


if __name__ == "__main__":
    unittest.main()
