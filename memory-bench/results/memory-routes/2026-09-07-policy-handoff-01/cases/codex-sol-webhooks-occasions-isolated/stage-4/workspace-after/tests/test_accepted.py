import unittest

from main import run


def receipt(record_id, account_id, delivery_id, occurred_at, payload=None):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": payload if payload is not None else f"payload:{record_id}",
    }


class Accepted(unittest.TestCase):
    def test_empty_receipts_use_current_protocol(self):
        self.assertEqual(
            run({"command": "accepted", "receipts": []}),
            {
                "protocol": "2",
                "accepted_count": 0,
                "duplicate_count": 0,
                "receipts": [],
            },
        )

    def test_returns_selected_receipts_unchanged_in_input_order(self):
        receipts = [
            receipt("old", "A", "shared", "2026-04-01T23:30:00-02:00"),
            receipt("other", "A", "other", "2026-04-02T01:15:00Z", "raw payload"),
            receipt("z-tie", "B", "shared", "2026-04-02T03:00:00+01:00"),
            receipt("a-tie", "C", "shared", "2026-04-01T19:00:00-07:00"),
        ]

        self.assertEqual(
            run({"command": "accepted", "protocol": "2", "receipts": receipts}),
            {
                "protocol": "2",
                "accepted_count": 2,
                "duplicate_count": 2,
                "receipts": [receipts[1], receipts[3]],
            },
        )

    def test_protocol_1_is_not_supported_for_accepted(self):
        self.assertEqual(
            run({"command": "accepted", "protocol": "1", "receipts": []}),
            {"error": "unknown_command"},
        )

    def test_existing_commands_remain_supported(self):
        request = {
            "command": "summary",
            "protocol": "1",
            "receipts": [
                receipt("one", "A", "shared", "2026-04-01T10:00:00Z"),
                receipt("two", "B", "shared", "2026-04-01T10:00:00Z"),
            ],
        }

        self.assertEqual(
            run(request),
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 0},
        )


if __name__ == "__main__":
    unittest.main()
