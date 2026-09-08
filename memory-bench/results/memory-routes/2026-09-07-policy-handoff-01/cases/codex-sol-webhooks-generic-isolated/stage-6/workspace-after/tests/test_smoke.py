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

    def test_accepted_returns_protocol_2_representatives_in_input_order(self):
        receipts = [
            {
                "record_id": "delivery-1-earlier",
                "account_id": "account-a",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-01T00:10:00+01:00",
                "payload": "duplicate across the UTC date boundary",
            },
            {
                "record_id": "delivery-2-winner",
                "account_id": "account-a",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-03-31T23:30:00Z",
                "payload": "first accepted representative in input order",
            },
            {
                "record_id": "delivery-1-winner",
                "account_id": "account-b",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-03-31T23:20:00Z",
                "payload": "later instant despite a different account",
            },
            {
                "record_id": "delivery-2-duplicate",
                "account_id": "account-c",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-03-31T23:29:59Z",
                "payload": "duplicate",
            },
        ]

        response = self.run_cli({"command": "accepted", "receipts": receipts})

        self.assertEqual(
            response,
            {
                "protocol": "2",
                "accepted_count": 2,
                "duplicate_count": 2,
                "receipts": [receipts[1], receipts[2]],
            },
        )

    def test_accepted_protocol_2_breaks_equal_instant_ties_by_record_id(self):
        receipts = [
            {
                "record_id": "z-record",
                "account_id": "account-a",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T01:00:00+01:00",
                "payload": "duplicate",
            },
            {
                "record_id": "a-record",
                "account_id": "account-b",
                "delivery_id": "delivery",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "accepted unchanged",
            },
        ]

        accepted = self.run_cli(
            {"command": "accepted", "protocol": "2", "receipts": receipts}
        )
        summary = self.run_cli(
            {"command": "summary", "protocol": "2", "receipts": receipts}
        )

        self.assertEqual(accepted["receipts"], [receipts[1]])
        self.assertEqual(
            {
                "protocol": accepted["protocol"],
                "accepted_count": accepted["accepted_count"],
                "duplicate_count": accepted["duplicate_count"],
            },
            summary,
        )

    def test_accepted_empty_batch(self):
        response = self.run_cli(
            {"command": "accepted", "protocol": "2", "receipts": []}
        )

        self.assertEqual(
            response,
            {
                "protocol": "2",
                "accepted_count": 0,
                "duplicate_count": 0,
                "receipts": [],
            },
        )

    def test_accepted_protocol_1_uses_original_provider_contract(self):
        receipts = [
            {
                "record_id": "delivery-2-winner",
                "account_id": "account-a",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-04-01T00:30:00+01:00",
                "payload": "earliest instant with original timestamp spelling",
            },
            {
                "record_id": "same-id-other-account",
                "account_id": "account-b",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-02T00:00:00Z",
                "payload": "separate account-scoped delivery",
            },
            {
                "record_id": "delivery-2-later",
                "account_id": "account-a",
                "delivery_id": "delivery-2",
                "occurred_at": "2026-03-31T23:45:00Z",
                "payload": "duplicate despite earlier local calendar date",
            },
            {
                "record_id": "z-record",
                "account_id": "account-a",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-01T01:00:00+01:00",
                "payload": "equal-instant duplicate by record id",
            },
            {
                "record_id": "a-record",
                "account_id": "account-a",
                "delivery_id": "delivery-1",
                "occurred_at": "2026-04-01T00:00:00Z",
                "payload": "equal-instant winner by record id",
            },
        ]

        response = self.run_cli(
            {"command": "accepted", "protocol": "1", "receipts": receipts}
        )

        self.assertEqual(
            response,
            {
                "protocol": "1",
                "accepted_count": 3,
                "duplicate_count": 2,
                "receipts": [receipts[0], receipts[1], receipts[4]],
            },
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
