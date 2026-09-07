import json
from pathlib import Path
import subprocess
import sys
import unittest


class ReconcileRegressionTests(unittest.TestCase):
    def reconcile(self, month, **kwargs):
        result = subprocess.run(
            [sys.executable, "cli.py"],
            input=json.dumps({"op": "reconcile", "month": month, **kwargs}),
            text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], check=True,
        )
        return json.loads(result.stdout)

    def test_bundled_february_close(self):
        self.assertEqual(self.reconcile("2025-02"), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200,
            "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_complete_calendar_months(self):
        for month, last_day, next_start in [
            ("2025-02", "2025-02-28", "2025-03-01"),
            ("2024-02", "2024-02-29", "2024-03-01"),
            ("2025-04", "2025-04-30", "2025-05-01"),
            ("2025-01", "2025-01-31", "2025-02-01"),
            ("2025-12", "2025-12-31", "2026-01-01"),
            ("2099-12", "2099-12-31", "2100-01-01"),
        ]:
            with self.subTest(month=month):
                rows = [
                    {"id": "next", "kind": "payment", "posted_at": next_start + "T00:00:00Z", "amount_cents": 9999},
                    {"id": "last-ms", "kind": "refund", "posted_at": last_day + "T23:59:59.999Z", "amount_cents": 40},
                    {"id": "last-day", "kind": "payment", "posted_at": last_day + "T00:00:00Z", "amount_cents": 200},
                    {"id": "start", "kind": "payment", "posted_at": month + "-01T00:00:00Z", "amount_cents": 100},
                    {"id": "before", "kind": "payment", "posted_at": month + "-01T00:59:59.999+01:00", "amount_cents": 9999},
                ]
                self.assertEqual(self.reconcile(month, transactions=rows), {
                    "month": month, "transaction_ids": ["start", "last-day", "last-ms"],
                    "payment_total_cents": 300, "refund_total_cents": 40,
                    "net_total_cents": 260,
                })

    def test_utc_offsets_and_tie_order(self):
        rows = [
            {"id": "outside", "kind": "payment", "posted_at": "2025-02-28T23:00:00-01:00", "amount_cents": 9999},
            {"id": "b", "kind": "refund", "posted_at": "2025-03-01T00:45:00+01:00", "amount_cents": 40},
            {"id": "a", "kind": "payment", "posted_at": "2025-02-28T23:45:00Z", "amount_cents": 200},
            {"id": "start", "kind": "payment", "posted_at": "2025-01-31T23:00:00-01:00", "amount_cents": 100},
        ]
        self.assertEqual(self.reconcile("2025-02", transactions=rows), {
            "month": "2025-02", "transaction_ids": ["start", "a", "b"],
            "payment_total_cents": 300, "refund_total_cents": 40,
            "net_total_cents": 260,
        })

    def test_empty_override(self):
        self.assertEqual(self.reconcile("2025-02", transactions=[]), {
            "month": "2025-02", "transaction_ids": [],
            "payment_total_cents": 0, "refund_total_cents": 0,
            "net_total_cents": 0,
        })


if __name__ == "__main__":
    unittest.main()
