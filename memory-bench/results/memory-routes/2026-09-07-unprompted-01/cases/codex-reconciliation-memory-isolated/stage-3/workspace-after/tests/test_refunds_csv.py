import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest


class RefundsCsvTests(unittest.TestCase):
    def request(self, op="refunds_csv", **kwargs):
        result = subprocess.run(
            [sys.executable, "cli.py"],
            input=json.dumps({"op": op, "month": "2025-02", **kwargs}),
            text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_bundled_refund(self):
        self.assertEqual(self.request(), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n",
        })

    def test_empty_and_payment_only(self):
        for rows in [[], [{"id": "payment", "kind": "payment",
                           "posted_at": "2025-02-15T12:00:00Z", "amount_cents": 50}]]:
            with self.subTest(rows=rows):
                self.assertEqual(self.request(transactions=rows), {
                    "month": "2025-02", "csv": "id,posted_at,amount_cents\n",
                })

    def test_month_membership_order_and_original_timestamps(self):
        rows = [
            {"id": "outside", "kind": "refund", "posted_at": "2025-02-28T23:00:00-01:00", "amount_cents": 999},
            {"id": "b", "kind": "refund", "posted_at": "2025-03-01T00:45:00+01:00", "amount_cents": 40},
            {"id": "a", "kind": "refund", "posted_at": "2025-02-28T23:45:00Z", "amount_cents": 20},
            {"id": "last", "kind": "refund", "posted_at": "2025-02-28T23:59:59.999Z", "amount_cents": 10},
            {"id": "payment", "kind": "payment", "posted_at": "2025-02-10T00:00:00Z", "amount_cents": 200},
            {"id": "start", "kind": "refund", "posted_at": "2025-01-31T23:00:00-01:00", "amount_cents": 0},
            {"id": "before", "kind": "refund", "posted_at": "2025-02-01T00:59:59.999+01:00", "amount_cents": 999},
        ]
        response = self.request(transactions=rows)
        self.assertEqual(response, {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\n"
                   "start,2025-01-31T23:00:00-01:00,0\n"
                   "a,2025-02-28T23:45:00Z,20\n"
                   "b,2025-03-01T00:45:00+01:00,40\n"
                   "last,2025-02-28T23:59:59.999Z,10\n",
        })
        detail = list(csv.DictReader(io.StringIO(response["csv"], newline="")))
        close = self.request(op="reconcile", transactions=rows)
        refund_ids = {row["id"] for row in rows if row["kind"] == "refund"}
        self.assertEqual([row["id"] for row in detail],
                         [id_ for id_ in close["transaction_ids"] if id_ in refund_ids])
        self.assertEqual(sum(int(row["amount_cents"]) for row in detail),
                         close["refund_total_cents"])

    def test_minimal_escaping(self):
        cases = [
            ("plain", "plain"),
            (" space ", " space "),
            ("", ""),
            ("a,b", '"a,b"'),
            ('a"b', '"a""b"'),
            ("a\rb", '"a\rb"'),
            ("a\nb", '"a\nb"'),
            ('a,\r\n"b', '"a,\r\n""b"'),
        ]
        for id_, escaped in cases:
            with self.subTest(id=id_):
                response = self.request(transactions=[{
                    "id": id_, "kind": "refund",
                    "posted_at": "2025-02-15T12:00:00Z", "amount_cents": 200,
                }])
                self.assertEqual(response["csv"], "id,posted_at,amount_cents\n"
                                 + escaped + ",2025-02-15T12:00:00Z,200\n")


if __name__ == "__main__":
    unittest.main()
