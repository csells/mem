import json
import subprocess
import sys
import unittest

from main import run


def receipt(record_id, account_id, delivery_id, occurred_at):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": f"payload:{record_id}",
    }


class Count(unittest.TestCase):
    def test_empty_receipts_use_current_protocol(self):
        self.assertEqual(
            run({"command": "count", "receipts": []}),
            {"protocol": "2", "accepted_count": 0, "duplicate_count": 0},
        )

    def test_counts_one_acceptance_per_delivery_identity(self):
        receipts = [
            receipt("later", "A", "D-1", "2026-04-01T10:00:00Z"),
            receipt("earlier", "A", "D-1", "2026-04-01T11:00:00+02:00"),
            receipt("other", "A", "D-2", "2026-04-01T12:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_delivery_ids_are_scoped_to_accounts(self):
        receipts = [
            receipt("one", "A", "D", "2026-04-01T10:00:00Z"),
            receipt("two", "B", "D", "2026-04-01T10:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "count", "protocol": "1", "receipts": receipts}),
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 0},
        )

    def test_protocol_2_delivery_ids_span_accounts(self):
        receipts = [
            receipt("one", "A", "D", "2026-04-01T10:00:00Z"),
            receipt("two", "B", "D", "2026-04-01T10:00:00Z"),
        ]

        self.assertEqual(
            run({"command": "count", "protocol": "2", "receipts": receipts}),
            {"protocol": "2", "accepted_count": 1, "duplicate_count": 1},
        )

    def test_cli_emits_one_response(self):
        request = {
            "command": "count",
            "protocol": "1",
            "receipts": [receipt("one", "A", "D", "2026-04-01T10:00:00Z")],
        }
        process = subprocess.run(
            [sys.executable, "main.py"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(
            json.loads(process.stdout),
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 0},
        )


if __name__ == "__main__":
    unittest.main()
