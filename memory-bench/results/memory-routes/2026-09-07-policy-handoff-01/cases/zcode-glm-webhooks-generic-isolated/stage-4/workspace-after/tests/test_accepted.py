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

def accepted(receipts, protocol=None):
    request = {"command": "accepted", "receipts": receipts}
    if protocol is not None:
        request["protocol"] = protocol
    return run_cli(request)

def counts_only(response):
    return {k: v for k, v in response.items() if k != "receipts"}

class Accepted(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(accepted([]),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0, "receipts": []})

    def test_single_receipt_returned_unchanged(self):
        sole = receipt("R-1", "2026-04-01T10:00:00Z")
        self.assertEqual(accepted([sole]),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [sole]})

    def test_response_has_exactly_the_named_fields(self):
        response = accepted([receipt("R-1", "2026-04-01T10:00:00Z")])
        self.assertEqual(set(response), {"protocol", "accepted_count", "duplicate_count", "receipts"})

    def test_winners_are_latest_instant_per_delivery_in_input_order(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", delivery_id="D-2"),
            receipt("R-2", "2026-04-01T12:00:00+02:00"),  # 10:00Z, latest for D-1
            receipt("R-3", "2026-04-01T09:00:00Z"),       # duplicate for D-1
        ]
        self.assertEqual(accepted(receipts)["receipts"], [receipts[0], receipts[1]])

    def test_winners_keep_original_timestamp_spelling(self):
        receipts = [
            receipt("R-2", "2026-04-01T10:00:00Z"),
            receipt("R-1", "2026-04-01T12:00:00+02:00"),  # same instant, smaller record_id
        ]
        self.assertEqual(accepted(receipts)["receipts"], [receipts[1]])

    def test_omitted_protocol_selects_current(self):
        receipts = [receipt("R-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(accepted(receipts), accepted(receipts, protocol="2"))

    def test_counts_equal_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T09:00:00Z", account_id="A"),
            receipt("R-3", "2026-04-01T08:00:00Z", account_id="B"),
        ]
        summary = run_cli({"command": "summary", "receipts": receipts})
        self.assertEqual(counts_only(accepted(receipts)), summary)

class ProtocolSupport(unittest.TestCase):
    def test_protocol_1_is_not_an_accepted_version(self):
        self.assertEqual(accepted([receipt("R-1", "2026-04-01T10:00:00Z")], protocol="1"),
                         {"error": "unknown_protocol"})

    def test_unknown_protocol_rejected(self):
        self.assertEqual(accepted([receipt("R-1", "2026-04-01T10:00:00Z")], protocol="3"),
                         {"error": "unknown_protocol"})

class PriorCommandsPreserved(unittest.TestCase):
    def test_count_and_summary_versions_remain_supported(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", account_id="A"),
            receipt("R-2", "2026-04-01T09:00:00Z", account_id="B"),
        ]
        self.assertEqual(run_cli({"command": "count", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})
        self.assertEqual(run_cli({"command": "summary", "protocol": "1", "receipts": receipts}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0})
        self.assertEqual(run_cli({"command": "count", "receipts": receipts}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})

if __name__ == "__main__":
    unittest.main()
