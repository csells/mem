import json
import subprocess
import sys
import unittest

RECEIPTS = [
    {"record_id": "R-3", "account_id": "A", "delivery_id": "D-1",
     "occurred_at": "2026-04-01T10:00:00Z", "payload": "a"},
    {"record_id": "R-1", "account_id": "B", "delivery_id": "D-1",
     "occurred_at": "2026-04-01T12:00:00+02:00", "payload": "b"},
    {"record_id": "R-2", "account_id": "A", "delivery_id": "D-1",
     "occurred_at": "2026-03-31T23:00:00-05:00", "payload": "c"},
    {"record_id": "R-4", "account_id": "C", "delivery_id": "D-2",
     "occurred_at": "2026-04-02T00:00:00Z", "payload": "d"},
]


def run(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


class Accepted(unittest.TestCase):
    def test_exact_fields_and_current_protocol(self):
        got = run({"command": "accepted", "receipts": RECEIPTS})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count", "receipts"})
        self.assertEqual(got["protocol"], "2")
        self.assertEqual(got["accepted_count"], 2)
        self.assertEqual(got["duplicate_count"], 2)
        # Latest UTC instant per delivery_id, ties -> smallest record_id; input order.
        self.assertEqual(got["receipts"], [RECEIPTS[1], RECEIPTS[3]])

    def test_explicit_2_matches_omitted(self):
        self.assertEqual(run({"command": "accepted", "protocol": "2", "receipts": RECEIPTS}),
                         run({"command": "accepted", "receipts": RECEIPTS}))

    def test_counts_equal_summary(self):
        for protocol in ({}, {"protocol": "1"}, {"protocol": "2"}):
            got = run({"command": "accepted", "receipts": RECEIPTS, **protocol})
            summary = run({"command": "summary", "receipts": RECEIPTS, **protocol})
            self.assertEqual({k: got[k] for k in summary}, summary)
            self.assertEqual(got["accepted_count"], len(got["receipts"]))

    def test_explicit_1_keeps_original_contract(self):
        got = run({"command": "accepted", "protocol": "1", "receipts": RECEIPTS})
        self.assertEqual(got["protocol"], "1")
        self.assertEqual([r["record_id"] for r in got["receipts"]], ["R-1", "R-2", "R-4"])

    def test_empty_and_single(self):
        self.assertEqual(run({"command": "accepted", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0, "receipts": []})
        self.assertEqual(run({"command": "accepted", "receipts": [RECEIPTS[2]]}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [RECEIPTS[2]]})

    def test_receipts_returned_unchanged(self):
        got = run({"command": "accepted", "receipts": RECEIPTS})
        for receipt in got["receipts"]:
            self.assertIn(receipt, RECEIPTS)
            self.assertEqual(set(receipt),
                             {"record_id", "account_id", "delivery_id", "occurred_at", "payload"})

    def test_unsupported_protocol(self):
        self.assertEqual(run({"command": "accepted", "protocol": "9", "receipts": RECEIPTS}),
                         {"error": "unsupported_protocol"})


if __name__ == "__main__":
    unittest.main()
