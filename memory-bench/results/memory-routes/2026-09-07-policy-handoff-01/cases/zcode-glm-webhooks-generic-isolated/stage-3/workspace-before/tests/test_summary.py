import json
import subprocess
import sys
import unittest

def run_cli(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)

def receipt(record_id, occurred_at, delivery_id="D-1", account_id="A"):
    return {"record_id": record_id, "account_id": account_id,
            "delivery_id": delivery_id, "occurred_at": occurred_at,
            "payload": "payload:" + record_id}

def summarized(receipts, protocol=None):
    request = {"command": "summary", "receipts": receipts}
    if protocol is not None:
        request["protocol"] = protocol
    return run_cli(request)

class Summary(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(summarized([]), {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(summarized([receipt("R-1", "2026-04-01T10:00:00Z")]),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(summarized([receipt("R-1", "2026-04-01T10:00:00Z")]),
                         summarized([receipt("R-1", "2026-04-01T10:00:00Z")], protocol="1"))

    def test_same_delivery_id_across_accounts_is_separate_deliveries(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T10:00:00Z", account_id="B"),
        ]
        self.assertEqual(summarized(receipts), {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})

    def test_duplicates_within_one_account(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T09:00:00Z", account_id="A"),
        ]
        self.assertEqual(summarized(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

    def test_cross_account_earliest_instant_wins_per_account(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T09:00:00Z", account_id="A"),
            receipt("R-3", "2026-04-01T08:00:00Z", account_id="B"),
            receipt("R-4", "2026-04-01T09:30:00Z", account_id="B"),
        ]
        self.assertEqual(summarized(receipts), {"protocol": "1", "accepted_count": 2, "duplicate_count": 2})

    def test_equal_instants_tiebreak_on_record_id(self):
        receipts = [
            receipt("R-2", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-1", "2026-04-01T12:00:00+02:00", account_id="A"),  # same instant, smaller record_id
        ]
        self.assertEqual(summarized(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

class CountPreserved(unittest.TestCase):
    def test_count_still_answers_for_single_account(self):
        request = {"command": "count", "protocol": "1",
                   "receipts": [receipt("R-1", "2026-04-01T10:00:00Z")]}
        self.assertEqual(run_cli(request),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

if __name__ == "__main__":
    unittest.main()
