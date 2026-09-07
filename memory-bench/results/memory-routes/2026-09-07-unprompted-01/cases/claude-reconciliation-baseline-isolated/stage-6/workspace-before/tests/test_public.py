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

    def test_february_close_includes_last_day_and_offset_tz(self):
        # p-offset-feb posts at 2025-03-01T00:45:00+01:00 = 2025-02-28T23:45:00Z — still in Feb ledger window
        # p-mar-open posts at 2025-03-01T00:00:00Z — before the 05:00 cutoff, also included in Feb
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

    def test_march_open_included_before_finance_cutoff(self):
        # p-mar-open posts at 2025-03-01T00:00:00Z, before the 05:00 finance cutoff — included in February
        request = {"op": "reconcile", "month": "2025-02"}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        ids = json.loads(result.stdout)["transaction_ids"]
        self.assertIn("p-mar-open", ids)

    def test_december_to_january_rollover(self):
        # jan-first at 2026-01-01T00:00:00Z is before the 05:00 finance cutoff — included in December
        request = {"op": "reconcile", "month": "2025-12", "transactions": [
            {"id": "dec-last", "kind": "payment", "posted_at": "2025-12-31T23:59:59Z", "amount_cents": 500},
            {"id": "jan-first", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 999},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-12",
            "transaction_ids": ["dec-last", "jan-first"],
            "payment_total_cents": 1499,
            "refund_total_cents": 0,
            "net_total_cents": 1499,
        })


if __name__ == "__main__":
    unittest.main()
