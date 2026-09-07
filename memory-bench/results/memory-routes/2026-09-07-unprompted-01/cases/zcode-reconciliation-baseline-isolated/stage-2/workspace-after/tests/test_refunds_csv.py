import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def refunds_csv(request):
    result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request),
                            text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


class RefundsCsvTests(unittest.TestCase):
    def test_february_refund_detail_from_snapshot(self):
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02"}), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n",
        })

    def test_month_without_refunds_is_header_only(self):
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-03"}), {
            "month": "2025-03",
            "csv": "id,posted_at,amount_cents\n",
        })

    def test_override_with_no_rows_is_header_only(self):
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": []}), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\n",
        })

    def test_payments_never_appear(self):
        rows = [
            {"id": "p-1", "kind": "payment", "posted_at": "2025-02-12T12:00:00Z", "amount_cents": 1250},
            {"id": "r-1", "kind": "refund", "posted_at": "2025-02-13T12:00:00Z", "amount_cents": 250},
        ]
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-1,2025-02-13T12:00:00Z,250\n",
        })

    def test_refunds_follow_reconcile_order(self):
        rows = [
            {"id": "r-late", "kind": "refund", "posted_at": "2025-02-20T00:00:00Z", "amount_cents": 700},
            {"id": "r-early-b", "kind": "refund", "posted_at": "2025-02-01T00:00:00Z", "amount_cents": 300},
            {"id": "r-early-a", "kind": "refund", "posted_at": "2025-02-01T00:00:00Z", "amount_cents": 100},
            {"id": "r-out", "kind": "refund", "posted_at": "2025-01-31T23:59:59Z", "amount_cents": 999},
        ]
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "csv": ("id,posted_at,amount_cents\n"
                    "r-early-a,2025-02-01T00:00:00Z,100\n"
                    "r-early-b,2025-02-01T00:00:00Z,300\n"
                    "r-late,2025-02-20T00:00:00Z,700\n"),
        })

    def test_offset_timestamp_buckets_by_instant_and_preserves_string(self):
        rows = [
            {"id": "r-offset", "kind": "refund", "posted_at": "2025-03-01T00:45:00+01:00", "amount_cents": 600},
            {"id": "r-mar", "kind": "refund", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 500},
        ]
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-offset,2025-03-01T00:45:00+01:00,600\n",
        })

    def test_fields_with_comma_quote_and_newline_are_minimally_quoted(self):
        rows = [
            {"id": 'a,b "c"\nd', "kind": "refund", "posted_at": "2025-02-15T12:00:00Z", "amount_cents": 200},
        ]
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "csv": 'id,posted_at,amount_cents\n"a,b ""c""\nd",2025-02-15T12:00:00Z,200\n',
        })

    def test_carriage_return_in_id_is_quoted(self):
        rows = [
            {"id": "customer\rreturn", "kind": "refund", "posted_at": "2025-02-15T12:00:00Z", "amount_cents": 200},
        ]
        self.assertEqual(refunds_csv({"op": "refunds_csv", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "csv": 'id,posted_at,amount_cents\n"customer\rreturn",2025-02-15T12:00:00Z,200\n',
        })


if __name__ == "__main__":
    unittest.main()
