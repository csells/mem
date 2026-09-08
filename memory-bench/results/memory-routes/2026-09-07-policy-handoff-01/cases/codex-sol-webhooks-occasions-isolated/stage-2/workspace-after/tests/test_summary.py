import unittest

from main import run


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
            {"protocol": "1", "accepted_count": 0, "duplicate_count": 0},
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


if __name__ == "__main__":
    unittest.main()
