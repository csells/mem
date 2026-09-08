import json
import subprocess
import sys
import unittest


class Protocols(unittest.TestCase):
    def check_counts(self, receipts, expected_by_protocol):
        for command in ("count", "summary"):
            for protocol in (None, "1", "2"):
                for ordered in (receipts, list(reversed(receipts))):
                    with self.subTest(command=command, protocol=protocol, receipts=ordered):
                        request = {"command": command, "receipts": ordered}
                        if protocol is not None:
                            request["protocol"] = protocol
                        result = subprocess.run(
                            [sys.executable, "main.py"], input=json.dumps(request),
                            text=True, capture_output=True, check=True,
                        )
                        actual_protocol = protocol or "2"
                        accepted, duplicates = expected_by_protocol[actual_protocol]
                        self.assertEqual(json.loads(result.stdout), {
                            "protocol": actual_protocol,
                            "accepted_count": accepted,
                            "duplicate_count": duplicates,
                        })

    def test_cross_account_identity_applies_to_all_dates(self):
        receipts = [
            {"record_id": "z", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2020-01-01T00:30:00+02:00", "payload": "old"},
            {"record_id": "a", "account_id": "B", "delivery_id": "D-1",
             "occurred_at": "2099-12-31T23:30:00-02:00", "payload": "new"},
            {"record_id": "é", "account_id": "B", "delivery_id": "D-1",
             "occurred_at": "2026-01-01T00:00:00Z", "payload": "repeat"},
            {"record_id": "中", "account_id": "A", "delivery_id": "D-2",
             "occurred_at": "2026-01-01T00:00:00Z", "payload": "repeat"},
        ]
        self.check_counts(receipts, {"1": (3, 1), "2": (2, 2)})

    def test_empty(self):
        self.check_counts([], {"1": (0, 0), "2": (0, 0)})

    def test_single_receipt(self):
        self.check_counts([
            {"record_id": "R", "account_id": "A", "delivery_id": "D",
             "occurred_at": "2026-01-01T00:00:00Z", "payload": "single"},
        ], {"1": (1, 0), "2": (1, 0)})
