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


class Protocol2(unittest.TestCase):
    def test_omitted_protocol_selects_2(self):
        for command in ("count", "summary"):
            self.assertEqual(run({"command": command, "receipts": RECEIPTS}),
                             {"protocol": "2", "accepted_count": 2, "duplicate_count": 2})

    def test_explicit_2_matches_omitted(self):
        self.assertEqual(run({"command": "summary", "protocol": "2", "receipts": RECEIPTS}),
                         run({"command": "summary", "receipts": RECEIPTS}))

    def test_explicit_1_keeps_original_contract(self):
        self.assertEqual(run({"command": "count", "protocol": "1", "receipts": RECEIPTS}),
                         {"protocol": "1", "accepted_count": 3, "duplicate_count": 1})

    def test_v2_latest_instant_then_smallest_record_id(self):
        import main
        self.assertEqual([r["record_id"] for r in main.accepted_receipts_v2(RECEIPTS)],
                         ["R-1", "R-4"])
        self.assertEqual([r["record_id"] for r in main.accepted_receipts_v1(RECEIPTS)],
                         ["R-1", "R-2", "R-4"])


if __name__ == "__main__":
    unittest.main()
