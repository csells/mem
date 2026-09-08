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

def counted(receipts, protocol=None):
    request = {"command": "count", "receipts": receipts}
    if protocol is not None:
        request["protocol"] = protocol
    return run_cli(request)

class Count(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(counted([]), {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        self.assertEqual(counted([receipt("R-1", "2026-04-01T10:00:00Z")]),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_selects_current(self):
        self.assertEqual(counted([receipt("R-1", "2026-04-01T10:00:00Z")]),
                         counted([receipt("R-1", "2026-04-01T10:00:00Z")], protocol="1"))

    def test_duplicates_same_delivery(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z"),
            receipt("R-2", "2026-04-01T09:00:00Z"),
            receipt("R-3", "2026-04-01T10:00:00Z"),
        ]
        self.assertEqual(counted(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 2})

    def test_offsets_compared_as_utc_instants(self):
        # 00:30+02:00 is 22:30Z on the prior calendar date, earlier than 23:00Z.
        receipts = [
            receipt("R-1", "2026-04-01T00:30:00+02:00"),
            receipt("R-2", "2026-03-31T23:00:00Z"),
        ]
        self.assertEqual(counted(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

    def test_negative_offset(self):
        receipts = [
            receipt("R-1", "2026-04-01T02:00:00-05:00"),  # 07:00Z
            receipt("R-2", "2026-04-01T08:00:00Z"),       # later instant
        ]
        self.assertEqual(counted(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

    def test_equal_instants_tiebreak_on_record_id(self):
        receipts = [
            receipt("R-2", "2026-04-01T10:00:00Z"),
            receipt("R-1", "2026-04-01T12:00:00+02:00"),  # same instant, smaller record_id
        ]
        self.assertEqual(counted(receipts), {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

    def test_distinct_deliveries(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", delivery_id="D-1"),
            receipt("R-2", "2026-04-01T10:00:00Z", delivery_id="D-2"),
        ]
        self.assertEqual(counted(receipts), {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})

class Regression(unittest.TestCase):
    def test_ping_preserved(self):
        self.assertEqual(run_cli({"command": "ping"}),
                         {"status": "ok", "product": "Courier Relay"})

    def test_unknown_command_preserved(self):
        self.assertEqual(run_cli({"command": "whatever"}), {"error": "unknown_command"})

if __name__ == "__main__":
    unittest.main()
