import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def replay(request):
    result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request),
                            text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


class Release1ReconcileTests(unittest.TestCase):
    def test_archived_release1_report_from_snapshot(self):
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02"}), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200,
            "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_first_instant_of_month_is_included(self):
        rows = [
            {"id": "month-open", "kind": "payment", "posted_at": "2025-02-01T00:00:00Z", "amount_cents": 600},
            {"id": "jan-close", "kind": "payment", "posted_at": "2025-01-31T23:59:59.999Z", "amount_cents": 100},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02", "transaction_ids": ["month-open"],
            "payment_total_cents": 600, "refund_total_cents": 0, "net_total_cents": 600,
        })

    def test_first_instant_of_next_month_is_excluded(self):
        rows = [
            {"id": "feb-close", "kind": "refund", "posted_at": "2025-02-28T23:59:59.999Z", "amount_cents": 300},
            {"id": "mar-open", "kind": "payment", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 500},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02", "transaction_ids": ["feb-close"],
            "payment_total_cents": 0, "refund_total_cents": 300, "net_total_cents": -300,
        })

    def test_offset_timestamps_bucket_by_absolute_instant(self):
        rows = [
            {"id": "jan-written", "kind": "payment", "posted_at": "2025-01-31T23:30:00-01:00", "amount_cents": 200},
            {"id": "feb-written", "kind": "payment", "posted_at": "2025-02-01T00:30:00+01:00", "amount_cents": 100},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02", "transaction_ids": ["jan-written"],
            "payment_total_cents": 200, "refund_total_cents": 0, "net_total_cents": 200,
        })

    def test_year_rollover_upper_cutoff_is_january_first(self):
        rows = [
            {"id": "dec-last", "kind": "payment", "posted_at": "2025-12-31T23:30:00Z", "amount_cents": 6400},
            {"id": "dec-offset", "kind": "payment", "posted_at": "2026-01-01T00:45:00+01:00", "amount_cents": 700},
            {"id": "jan-open", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 100},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-12", "transactions": rows}), {
            "month": "2025-12", "transaction_ids": ["dec-last", "dec-offset"],
            "payment_total_cents": 7100, "refund_total_cents": 0, "net_total_cents": 7100,
        })

    def test_ties_order_lexicographically_by_id(self):
        rows = [
            {"id": "b", "kind": "payment", "posted_at": "2025-06-15T12:00:00Z", "amount_cents": 100},
            {"id": "a", "kind": "refund", "posted_at": "2025-06-15T12:00:00Z", "amount_cents": 25},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-06", "transactions": rows}), {
            "month": "2025-06", "transaction_ids": ["a", "b"],
            "payment_total_cents": 100, "refund_total_cents": 25, "net_total_cents": 75,
        })

    def test_empty_override_returns_zero_totals(self):
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02", "transactions": []}), {
            "month": "2025-02", "transaction_ids": [],
            "payment_total_cents": 0, "refund_total_cents": 0, "net_total_cents": 0,
        })

    def test_coexists_with_active_cutoff_reports(self):
        rows = [
            {"id": "early", "kind": "payment", "posted_at": "2025-02-01T02:00:00Z", "amount_cents": 100},
            {"id": "late", "kind": "payment", "posted_at": "2025-02-28T20:00:00Z", "amount_cents": 200},
        ]
        self.assertEqual(replay({"op": "release1_reconcile", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02", "transaction_ids": ["early", "late"],
            "payment_total_cents": 300, "refund_total_cents": 0, "net_total_cents": 300,
        })
        self.assertEqual(replay({"op": "reconcile", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02", "transaction_ids": ["late"],
            "payment_total_cents": 200, "refund_total_cents": 0, "net_total_cents": 200,
        })


if __name__ == "__main__":
    unittest.main()
