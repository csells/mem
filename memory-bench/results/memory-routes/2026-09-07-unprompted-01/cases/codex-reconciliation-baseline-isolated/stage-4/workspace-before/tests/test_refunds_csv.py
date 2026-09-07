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
            [sys.executable, str(Path(__file__).resolve().parents[1] / "cli.py")],
            input=json.dumps({"op": op, "month": "2025-02", **kwargs}),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_bundled_refund(self):
        self.assertEqual(self.request(), {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n",
        })

    def test_minimal_escaping(self):
        cases = [
            ("plain", "plain"),
            (" spaced ", " spaced "),
            ("", ""),
            ("a,b", '"a,b"'),
            ('a"b', '"a""b"'),
            ("a\rb", '"a\rb"'),
            ("a\nb", '"a\nb"'),
            ('a,\r\n"b', '"a,\r\n""b"'),
        ]
        for identifier, escaped in cases:
            with self.subTest(identifier=identifier):
                self.assertEqual(self.request(transactions=[{
                    "id": identifier, "kind": "refund",
                    "posted_at": "2025-02-15T13:00:00+01:00", "amount_cents": 0,
                }]), {
                    "month": "2025-02",
                    "csv": "id,posted_at,amount_cents\n"
                           + escaped + ",2025-02-15T13:00:00+01:00,0\n",
                })

    def test_reconcile_membership_and_order(self):
        rows = [
            ("next", "refund", "2025-02-28T23:00:00-01:00", 900),
            ("z-last", "refund", "2025-02-28T23:59:59.999Z", 40),
            ("before", "refund", "2025-02-01T00:59:59.999+01:00", 800),
            ("a-last", "refund", "2025-03-01T00:59:59.999+01:00", 30),
            ("first", "refund", "2025-01-31T23:00:00-01:00", 20),
            ("payment", "payment", "2025-02-15T00:00:00Z", 100),
        ]
        transactions = [dict(id=id_, kind=kind, posted_at=posted, amount_cents=amount)
                        for id_, kind, posted, amount in rows]
        response = self.request(transactions=transactions)
        self.assertEqual(response, {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\n"
                   "first,2025-01-31T23:00:00-01:00,20\n"
                   "a-last,2025-03-01T00:59:59.999+01:00,30\n"
                   "z-last,2025-02-28T23:59:59.999Z,40\n",
        })
        exported = list(csv.DictReader(io.StringIO(response["csv"], newline="")))
        close = self.request(op="reconcile", transactions=transactions)
        refund_ids = {row["id"] for row in transactions if row["kind"] == "refund"}
        self.assertEqual([row["id"] for row in exported],
                         [id_ for id_ in close["transaction_ids"] if id_ in refund_ids])
        self.assertEqual(sum(int(row["amount_cents"]) for row in exported),
                         close["refund_total_cents"])

    def test_no_refunds(self):
        for transactions in [[], [{
            "id": "payment", "kind": "payment",
            "posted_at": "2025-02-15T00:00:00Z", "amount_cents": 100,
        }], [{
            "id": "outside", "kind": "refund",
            "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 100,
        }]]:
            with self.subTest(transactions=transactions):
                self.assertEqual(self.request(transactions=transactions), {
                    "month": "2025-02", "csv": "id,posted_at,amount_cents\n",
                })


if __name__ == "__main__":
    unittest.main()
