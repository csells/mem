import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def reconcile(request):
    result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request),
                            text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


class MonthCloseTests(unittest.TestCase):
    def test_february_close_from_snapshot(self):
        self.assertEqual(reconcile({"op": "reconcile", "month": "2025-02"}), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb", "p-mar-open"],
            "payment_total_cents": 24200,
            "refund_total_cents": 400,
            "net_total_cents": 23800,
        })

    def test_last_day_rows_and_next_month_boundary(self):
        rows = [
            {"id": "jan-last", "kind": "payment", "posted_at": "2025-01-31T23:59:59Z", "amount_cents": 3100},
            {"id": "feb-open", "kind": "payment", "posted_at": "2025-02-01T00:00:00Z", "amount_cents": 999},
            {"id": "feb-cutoff", "kind": "payment", "posted_at": "2025-02-01T05:00:00Z", "amount_cents": 77},
        ]
        self.assertEqual(reconcile({"op": "reconcile", "month": "2025-01", "transactions": rows}), {
            "month": "2025-01", "transaction_ids": ["jan-last", "feb-open"],
            "payment_total_cents": 4099, "refund_total_cents": 0, "net_total_cents": 4099,
        })

    def test_thirty_day_month_close(self):
        rows = [
            {"id": "apr-last", "kind": "refund", "posted_at": "2025-04-30T12:00:00Z", "amount_cents": 500},
            {"id": "may-open", "kind": "payment", "posted_at": "2025-05-01T00:00:00Z", "amount_cents": 800},
        ]
        self.assertEqual(reconcile({"op": "reconcile", "month": "2025-04", "transactions": rows}), {
            "month": "2025-04", "transaction_ids": ["apr-last", "may-open"],
            "payment_total_cents": 800, "refund_total_cents": 500, "net_total_cents": 300,
        })

    def test_leap_year_february_includes_twenty_ninth(self):
        rows = [
            {"id": "leap-day", "kind": "payment", "posted_at": "2024-03-01T00:45:00+01:00", "amount_cents": 2900},
            {"id": "mar-open", "kind": "payment", "posted_at": "2024-03-01T00:00:00Z", "amount_cents": 300},
        ]
        self.assertEqual(reconcile({"op": "reconcile", "month": "2024-02", "transactions": rows}), {
            "month": "2024-02", "transaction_ids": ["leap-day", "mar-open"],
            "payment_total_cents": 3200, "refund_total_cents": 0, "net_total_cents": 3200,
        })

    def test_year_rollover_december_close(self):
        rows = [
            {"id": "dec-last", "kind": "payment", "posted_at": "2026-01-01T00:45:00+01:00", "amount_cents": 6400},
            {"id": "jan-open", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 100},
        ]
        self.assertEqual(reconcile({"op": "reconcile", "month": "2025-12", "transactions": rows}), {
            "month": "2025-12", "transaction_ids": ["dec-last", "jan-open"],
            "payment_total_cents": 6500, "refund_total_cents": 0, "net_total_cents": 6500,
        })


if __name__ == "__main__":
    unittest.main()
