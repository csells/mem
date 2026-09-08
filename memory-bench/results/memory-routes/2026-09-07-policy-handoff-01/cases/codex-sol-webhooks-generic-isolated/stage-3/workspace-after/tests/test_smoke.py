import json
import subprocess
import sys
import unittest

class Smoke(unittest.TestCase):
    def test_ping(self):
        p = subprocess.run([sys.executable, "main.py"], input='{"command":"ping"}', text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p.stdout), {"status":"ok","product":"Courier Relay"})

    def test_count_uses_current_protocol_when_omitted(self):
        receipts = [
            {
                "record_id": "later",
                "account_id": "account",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-01T00:30:00+01:00",
                "payload": "later input, earlier instant",
            },
            {
                "record_id": "earlier-input",
                "account_id": "account",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-03-31T23:45:00Z",
                "payload": "duplicate",
            },
            {
                "record_id": "other-delivery",
                "account_id": "account",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-03-31T23:45:00Z",
                "payload": "accepted",
            },
        ]

        response = self.run_cli({"command": "count", "receipts": receipts})

        self.assertEqual(
            response,
            {"protocol": "2", "accepted_count": 2, "duplicate_count": 1},
        )

    def test_count_breaks_equal_instant_ties_without_changing_counts(self):
        receipts = [
            {
                "record_id": "z-record",
                "account_id": "account",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T01:00:00+01:00",
                "payload": "duplicate",
            },
            {
                "record_id": "a-record",
                "account_id": "account",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "accepted by record id",
            },
        ]

        response = self.run_cli(
            {"command": "count", "protocol": "1", "receipts": receipts}
        )

        self.assertEqual(
            response,
            {"protocol": "1", "accepted_count": 1, "duplicate_count": 1},
        )

    def test_summary_protocol_2_counts_delivery_identity_across_accounts(self):
        receipts = [
            {
                "record_id": "account-a-later",
                "account_id": "account-a",
                "delivery_id": "shared-delivery-id",
                "occurred_at": "2026-04-01T00:30:00+01:00",
                "payload": "duplicate for account-a",
            },
            {
                "record_id": "account-b",
                "account_id": "account-b",
                "delivery_id": "shared-delivery-id",
                "occurred_at": "2026-03-31T23:00:00Z",
                "payload": "duplicate despite the different account",
            },
            {
                "record_id": "account-a-earlier",
                "account_id": "account-a",
                "delivery_id": "shared-delivery-id",
                "occurred_at": "2026-03-31T23:15:00Z",
                "payload": "accepted for account-a",
            },
        ]

        response = self.run_cli({"command": "summary", "receipts": receipts})

        self.assertEqual(
            response,
            {"protocol": "2", "accepted_count": 1, "duplicate_count": 2},
        )

    def test_protocol_2_accepts_latest_instant_and_breaks_tie_by_record_id(self):
        receipts = [
            {
                "record_id": "latest-z-record",
                "account_id": "account-a",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T01:00:00+01:00",
                "payload": "duplicate by record id",
            },
            {
                "record_id": "earlier",
                "account_id": "account-b",
                "delivery_id": "delivery",
                "occurred_at": "2026-03-31T23:59:59Z",
                "payload": "duplicate by time",
            },
            {
                "record_id": "latest-a-record",
                "account_id": "account-c",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "accepted by record id",
            },
        ]

        response = self.run_cli(
            {"command": "count", "protocol": "2", "receipts": receipts}
        )

        self.assertEqual(
            response,
            {"protocol": "2", "accepted_count": 1, "duplicate_count": 2},
        )

    def test_explicit_protocol_1_keeps_account_scoped_delivery_identity(self):
        receipts = [
            {
                "record_id": "account-a",
                "account_id": "account-a",
                "delivery_id": "shared-delivery-id",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "accepted for account a",
            },
            {
                "record_id": "account-b",
                "account_id": "account-b",
                "delivery_id": "shared-delivery-id",
                "occurred_at": "2026-04-02T00:00:00Z",
                "payload": "accepted for account b",
            },
        ]

        response = self.run_cli(
            {"command": "summary", "protocol": "1", "receipts": receipts}
        )

        self.assertEqual(
            response,
            {"protocol": "1", "accepted_count": 2, "duplicate_count": 0},
        )

    def test_summary_supports_explicit_protocol_1_for_empty_batch(self):
        response = self.run_cli(
            {"command": "summary", "protocol": "1", "receipts": []}
        )

        self.assertEqual(
            response,
            {"protocol": "1", "accepted_count": 0, "duplicate_count": 0},
        )

    def run_cli(self, request):
        process = subprocess.run(
            [sys.executable, "main.py"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(process.stdout)
