import json
import subprocess
import sys
import unittest


def receipt(record_id, occurred_at, delivery_id="D-1", account_id="A", payload=None):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": payload if payload is not None else "payload:" + record_id,
    }


class AcceptedEndToEnd(unittest.TestCase):
    def cli(self, request):
        proc = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                              text=True, capture_output=True, check=True)
        return json.loads(proc.stdout)

    def accepted(self, protocol_receipts, **request_extra):
        request = {"command": "accepted", "receipts": protocol_receipts}
        request.update(request_extra)
        return self.cli(request)

    def test_empty(self):
        self.assertEqual(self.accepted([], protocol="2"),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0,
                          "receipts": []})

    def test_single_receipt_returned_unchanged(self):
        only = receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A",
                       payload="payload:R-1")
        self.assertEqual(self.accepted([only], protocol="2"),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": [only]})

    def test_omitted_protocol_selects_current(self):
        receipts = [receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
                    receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B")]
        self.assertEqual(self.accepted(receipts),
                         self.accepted(receipts, protocol="2"))

    def test_protocol_2_cross_account_identity_keeps_latest(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
            receipt("R-3", "2026-04-01T09:00:00Z", "D-1", account_id="C"),
        ]
        self.assertEqual(self.accepted(receipts, protocol="2"),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 2,
                          "receipts": [receipts[1]]})

    def test_protocol_2_latest_instant_with_equal_instant_tie(self):
        # Same delivery_id across accounts: 2026-04-01T23:00:00Z is later than
        # 2026-04-02T00:30:00+02:00 (22:30Z); the third shares the winner's
        # instant, so the smallest record_id wins the tie.
        receipts = [
            receipt("R-b", "2026-04-02T00:30:00+02:00", "D-1", account_id="A"),
            receipt("R-a", "2026-04-01T23:00:00Z", "D-1", account_id="B"),
            receipt("R-c", "2026-04-01T21:00:00-02:00", "D-1", account_id="C"),
        ]
        self.assertEqual(self.accepted(receipts, protocol="2"),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 2,
                          "receipts": [receipts[1]]})

    def test_representatives_unchanged_in_original_input_order(self):
        # Winners of D-1 and D-2 appear in input positions 1 then 0; the kept
        # receipt retains its offset timestamp spelling and payload.
        winner_d1 = receipt("R-2", "2026-04-01T01:30:00+02:00", "D-1", account_id="A",
                            payload="body text")
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-2", account_id="B"),
            winner_d1,
            receipt("R-3", "2026-03-31T23:00:00Z", "D-1", account_id="C"),
        ]
        self.assertEqual(self.accepted(receipts, protocol="2")["receipts"],
                         [receipts[0], winner_d1])

    def test_counts_equal_summary_for_same_request(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
            receipt("R-3", "2026-04-01T09:00:00Z", "D-2", account_id="A"),
        ]
        response = self.accepted(receipts, protocol="2")
        summary = self.cli({"command": "summary", "protocol": "2", "receipts": receipts})
        for field in ("protocol", "accepted_count", "duplicate_count"):
            self.assertEqual(response[field], summary[field])
        self.assertEqual(response["accepted_count"], len(response["receipts"]))

    def test_explicit_protocol_1_keeps_account_scoped_identity(self):
        receipts = [
            receipt("R-1", "2026-04-01T10:00:00Z", "D-1", account_id="A"),
            receipt("R-2", "2026-04-01T11:00:00Z", "D-1", account_id="B"),
        ]
        self.assertEqual(self.accepted(receipts, protocol="1"),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 0,
                          "receipts": receipts})

    def test_unsupported_protocol(self):
        self.assertEqual(self.accepted([], protocol="9"), {"error": "unsupported_protocol"})
