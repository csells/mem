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


class AcceptedProtocol1(unittest.TestCase):
    """Explicit "protocol":"1" exports representatives under the original
    provider contract (vendor/protocol-1.md), issue trial-0o0."""

    def test_exact_fields_and_protocol(self):
        got = run({"command": "accepted", "protocol": "1", "receipts": RECEIPTS})
        self.assertEqual(set(got), {"protocol", "accepted_count", "duplicate_count", "receipts"})
        self.assertEqual(got["protocol"], "1")
        self.assertEqual(got["accepted_count"], 3)
        self.assertEqual(got["duplicate_count"], 1)
        # (account_id, delivery_id) identity; earliest UTC instant wins;
        # cross-offset comparison (R-2 is 2026-04-01T04:00:00Z); input order kept.
        self.assertEqual(got["receipts"], [RECEIPTS[1], RECEIPTS[2], RECEIPTS[3]])

    def test_same_delivery_id_under_other_account_is_separate(self):
        receipts = [
            {"record_id": "R-1", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T10:00:00Z", "payload": "a"},
            {"record_id": "R-2", "account_id": "B", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T09:00:00Z", "payload": "b"},
        ]
        got = run({"command": "accepted", "protocol": "1", "receipts": receipts})
        self.assertEqual(got["accepted_count"], 2)
        self.assertEqual(got["duplicate_count"], 0)
        self.assertEqual(got["receipts"], receipts)
        # Under protocol 2 the same input collapses to one delivery.
        self.assertEqual(run({"command": "accepted", "receipts": receipts})["accepted_count"], 1)

    def test_tie_uses_smallest_record_id_by_code_point(self):
        receipts = [
            {"record_id": "R-b", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T10:00:00Z", "payload": "x"},
            {"record_id": "R-B", "account_id": "A", "delivery_id": "D-1",
             "occurred_at": "2026-04-01T12:00:00+02:00", "payload": "y"},
        ]
        got = run({"command": "accepted", "protocol": "1", "receipts": receipts})
        self.assertEqual(got["receipts"], [receipts[1]])
        self.assertEqual(got["duplicate_count"], 1)

    def test_counts_equal_count_and_summary(self):
        got = run({"command": "accepted", "protocol": "1", "receipts": RECEIPTS})
        for command in ("count", "summary"):
            other = run({"command": command, "protocol": "1", "receipts": RECEIPTS})
            self.assertEqual({k: got[k] for k in other}, other)

    def test_empty_and_single(self):
        self.assertEqual(run({"command": "accepted", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0, "receipts": []})
        self.assertEqual(run({"command": "accepted", "protocol": "1", "receipts": [RECEIPTS[0]]}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [RECEIPTS[0]]})

    def test_omitted_protocol_stays_current(self):
        got = run({"command": "accepted", "receipts": RECEIPTS})
        self.assertEqual(got["protocol"], "2")
        self.assertNotEqual(got["receipts"],
                            run({"command": "accepted", "protocol": "1", "receipts": RECEIPTS})["receipts"])


if __name__ == "__main__":
    unittest.main()
