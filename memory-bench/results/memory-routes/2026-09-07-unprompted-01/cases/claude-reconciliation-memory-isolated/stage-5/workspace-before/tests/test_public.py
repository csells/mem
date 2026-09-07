import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider import LedgerLake


class PublicTests(unittest.TestCase):
    def test_midmonth_reconciliation(self):
        request = {"op": "reconcile", "month": "2025-02", "transactions": [
            {"id": "p", "kind": "payment", "posted_at": "2025-02-12T00:00:00Z", "amount_cents": 1250},
            {"id": "r", "kind": "refund", "posted_at": "2025-02-13T00:00:00Z", "amount_cents": 250},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-02", "transaction_ids": ["p", "r"],
            "payment_total_cents": 1250, "refund_total_cents": 250, "net_total_cents": 1000,
        })

    def test_provider_time_range(self):
        rows = [{"id": "edge", "kind": "payment", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 1}]
        client = LedgerLake(rows)
        self.assertEqual(client.list_transactions(created_from="2025-02-01T00:00:00Z",
                                                  created_to="2025-03-01T00:00:00Z"), [])

    def test_february_full_close_with_fixture(self):
        request = {"op": "reconcile", "month": "2025-02"}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb", "p-mar-open"],
            "payment_total_cents": 24200,
            "refund_total_cents": 400,
            "net_total_cents": 23800,
        })

    def test_february_full_close_with_transactions(self):
        request = {"op": "reconcile", "month": "2025-02", "transactions": [
            {"id": "p-mar-open", "kind": "payment", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 9000},
            {"id": "p-feb-mid", "kind": "payment", "posted_at": "2025-02-10T12:00:00Z", "amount_cents": 12000},
            {"id": "p-feb-last", "kind": "payment", "posted_at": "2025-02-28T00:00:00Z", "amount_cents": 2500},
            {"id": "r-feb-last", "kind": "refund", "posted_at": "2025-02-28T17:30:00Z", "amount_cents": 400},
            {"id": "p-offset-feb", "kind": "payment", "posted_at": "2025-03-01T00:45:00+01:00", "amount_cents": 700},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb", "p-mar-open"],
            "payment_total_cents": 24200,
            "refund_total_cents": 400,
            "net_total_cents": 23800,
        })

    def test_december_year_rollover(self):
        request = {"op": "reconcile", "month": "2025-12", "transactions": [
            {"id": "dec", "kind": "payment", "posted_at": "2025-12-31T23:59:59Z", "amount_cents": 500},
            {"id": "jan", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 100},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-12",
            "transaction_ids": ["dec", "jan"],
            "payment_total_cents": 600,
            "refund_total_cents": 0,
            "net_total_cents": 600,
        })


if __name__ == "__main__":
    unittest.main()
