import unittest

from main import run


def receipt(record_id, account_id, delivery_id, occurred_at, payload=None):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": payload if payload is not None else "payload:" + record_id,
    }


class AcceptedReceipts(unittest.TestCase):
    def test_empty_and_omitted_protocol(self):
        self.assertEqual(
            run({"command": "accepted", "receipts": []}),
            {
                "protocol": "2",
                "accepted_count": 0,
                "duplicate_count": 0,
                "receipts": [],
            },
        )

    def test_returns_protocol_two_representatives_in_input_order(self):
        duplicate = receipt("old", "A", "D-1", "2026-04-01T10:00:00Z")
        replacement = receipt("new", "A", "D-1", "2026-04-01T12:00:00+02:00")
        other = receipt("other", "B", "D-2", "2026-04-01T09:00:00Z")

        result = run(
            {
                "command": "accepted",
                "protocol": "2",
                "receipts": [duplicate, replacement, other],
            }
        )

        self.assertEqual(result["protocol"], "2")
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["receipts"], [replacement, other])

    def test_accepted_receipt_keeps_original_fields(self):
        original = receipt(
            "R-1", "A", "D-1", "2026-04-01T10:00:00-07:00", payload="raw"
        )
        self.assertEqual(
            run({"command": "accepted", "receipts": [original]})["receipts"],
            [original],
        )


if __name__ == "__main__":
    unittest.main()
