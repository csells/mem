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

    def test_refunds_csv(self):
        request = {"op": "refunds_csv", "month": "2025-02", "transactions": [
            {"id": "p-feb-mid", "kind": "payment", "posted_at": "2025-02-10T12:00:00Z", "amount_cents": 12000},
            {"id": "p-feb-last", "kind": "payment", "posted_at": "2025-02-28T00:00:00Z", "amount_cents": 2500},
            {"id": "r-feb-last", "kind": "refund", "posted_at": "2025-02-28T17:30:00Z", "amount_cents": 400},
            {"id": "r-feb-first", "kind": "refund", "posted_at": "2025-02-01T10:00:00Z", "amount_cents": 200},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        expected = {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-feb-first,2025-02-01T10:00:00Z,200\nr-feb-last,2025-02-28T17:30:00Z,400\n"
        }
        self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
