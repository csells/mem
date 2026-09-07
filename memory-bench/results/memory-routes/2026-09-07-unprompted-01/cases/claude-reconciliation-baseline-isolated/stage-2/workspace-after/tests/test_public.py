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
        # p-offset-feb posts at 2025-03-01T00:45:00+01:00 = 2025-02-28T23:45:00Z — still February UTC
        request = {"op": "reconcile", "month": "2025-02"}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200,
            "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_march_open_excluded_from_february(self):
        # p-mar-open posts at 2025-03-01T00:00:00Z and must not appear in February
        request = {"op": "reconcile", "month": "2025-02"}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        ids = json.loads(result.stdout)["transaction_ids"]
        self.assertNotIn("p-mar-open", ids)

    def test_december_to_january_rollover(self):
        request = {"op": "reconcile", "month": "2025-12", "transactions": [
            {"id": "dec-last", "kind": "payment", "posted_at": "2025-12-31T23:59:59Z", "amount_cents": 500},
            {"id": "jan-first", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 999},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-12",
            "transaction_ids": ["dec-last"],
            "payment_total_cents": 500,
            "refund_total_cents": 0,
            "net_total_cents": 500,
        })


if __name__ == "__main__":
    unittest.main()
