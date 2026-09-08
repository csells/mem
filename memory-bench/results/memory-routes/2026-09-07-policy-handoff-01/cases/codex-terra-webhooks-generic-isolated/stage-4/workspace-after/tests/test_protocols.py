import unittest

from main import accepted_receipts, run


def receipt(record_id, account_id, delivery_id, occurred_at):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": "payload:" + record_id,
    }


class ProtocolTests(unittest.TestCase):
    def test_protocol_2_is_the_default_and_uses_account_delivery_identity(self):
        receipts = [
            receipt("old", "a", "d", "2026-04-01T10:00:00Z"),
            receipt("other-account", "b", "d", "2026-04-01T11:00:00Z"),
            receipt("new", "a", "d", "2026-04-01T12:00:00Z"),
        ]
        self.assertEqual(
            run({"command": "count", "receipts": receipts}),
            {"protocol": "2", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_protocol_1_remains_available_with_earliest_selection(self):
        receipts = [
            receipt("later", "a", "d", "2026-04-01T12:00:00Z"),
            receipt("earlier", "b", "d", "2026-04-01T10:00:00Z"),
        ]
        self.assertEqual(
            run({"command": "summary", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )
        self.assertEqual(accepted_receipts(receipts, "1"), [receipts[1]])

    def test_protocol_2_uses_utc_instants_ties_and_input_order(self):
        receipts = [
            receipt("z", "a", "first", "2026-04-02T00:30:00+01:00"),
            receipt("keep-second", "a", "second", "2026-04-02T01:00:00Z"),
            receipt("a", "a", "first", "2026-04-01T23:30:00Z"),
            receipt("latest", "a", "first", "2026-04-02T00:00:00Z"),
            receipt("z-tie", "a", "tie", "2026-04-02T01:30:00+01:00"),
            receipt("a-tie", "a", "tie", "2026-04-02T00:30:00Z"),
        ]
        self.assertEqual(
            accepted_receipts(receipts, "2"), [receipts[1], receipts[3], receipts[5]]
        )


if __name__ == "__main__":
    unittest.main()
