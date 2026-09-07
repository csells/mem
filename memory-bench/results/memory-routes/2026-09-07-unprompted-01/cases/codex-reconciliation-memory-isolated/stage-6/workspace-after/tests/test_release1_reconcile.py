import json
from pathlib import Path
import subprocess
import sys
import unittest


class Release1ReconcileTests(unittest.TestCase):
    def request(self, month, op="release1_reconcile", **kwargs):
        result = subprocess.run(
            [sys.executable, "cli.py"],
            input=json.dumps({"op": op, "month": month, **kwargs}),
            text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_bundled_fixture(self):
        self.assertEqual(self.request("2025-02"), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200, "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_calendar_boundaries_offsets_and_ties(self):
        for month, last_day, next_start in [
            ("2000-02", "2000-02-29", "2000-03-01"),
            ("2025-02", "2025-02-28", "2025-03-01"),
            ("2025-04", "2025-04-30", "2025-05-01"),
            ("2025-07", "2025-07-31", "2025-08-01"),
            ("2099-12", "2099-12-31", "2100-01-01"),
        ]:
            with self.subTest(month=month):
                rows = [
                    {"id": "next", "kind": "payment", "posted_at": next_start + "T00:00:00Z", "amount_cents": 9999},
                    {"id": "last-ms", "kind": "refund", "posted_at": last_day + "T23:59:59.999Z", "amount_cents": 400},
                    {"id": "b", "kind": "refund", "posted_at": next_start + "T00:45:00+01:00", "amount_cents": 40},
                    {"id": "a", "kind": "payment", "posted_at": last_day + "T23:45:00Z", "amount_cents": 200},
                    {"id": "start", "kind": "payment", "posted_at": month + "-01T00:00:00Z", "amount_cents": 100},
                    {"id": "before", "kind": "payment", "posted_at": month + "-01T00:59:59.999+01:00", "amount_cents": 9999},
                ]
                self.assertEqual(self.request(month, transactions=rows), {
                    "month": month, "transaction_ids": ["start", "a", "b", "last-ms"],
                    "payment_total_cents": 300, "refund_total_cents": 440,
                    "net_total_cents": -140,
                })

    def test_empty_override(self):
        self.assertEqual(self.request("2025-02", transactions=[]), {
            "month": "2025-02", "transaction_ids": [],
            "payment_total_cents": 0, "refund_total_cents": 0,
            "net_total_cents": 0,
        })

    def test_all_reports_with_same_input(self):
        rows = [
            {"id": "start", "kind": "payment", "posted_at": "2025-01-31T23:00:00-01:00", "amount_cents": 100},
            {"id": "cutoff", "kind": "payment", "posted_at": "2025-02-01T05:00:00Z", "amount_cents": 200},
            {"id": "next", "kind": "refund", "posted_at": "2025-03-01T01:00:00+01:00", "amount_cents": 30},
        ]
        for op in ("release1_reconcile", "incident_replay"):
            with self.subTest(op=op):
                self.assertEqual(self.request("2025-02", op, transactions=rows), {
                    "month": "2025-02", "transaction_ids": ["start", "cutoff"],
                    "payment_total_cents": 300, "refund_total_cents": 0,
                    "net_total_cents": 300,
                })
        self.assertEqual(self.request("2025-02", "reconcile", transactions=rows), {
            "month": "2025-02", "transaction_ids": ["cutoff", "next"],
            "payment_total_cents": 200, "refund_total_cents": 30,
            "net_total_cents": 170,
        })
        self.assertEqual(self.request("2025-02", "refunds_csv", transactions=rows), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nnext,2025-03-01T01:00:00+01:00,30\n",
        })
        self.assertEqual(self.request("2025-02", "daily_net", transactions=rows), {
            "month": "2025-02", "days": [
                {"date": "2025-02-01", "payment_total_cents": 200,
                 "refund_total_cents": 0, "net_total_cents": 200},
                {"date": "2025-02-28", "payment_total_cents": 0,
                 "refund_total_cents": 30, "net_total_cents": -30},
            ],
        })


if __name__ == "__main__":
    unittest.main()
