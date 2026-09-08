import json
import subprocess
import sys
import unittest


def receipt(record_id, delivery_id, occurred_at, account_id="A"):
    return {
        "record_id": record_id,
        "account_id": account_id,
        "delivery_id": delivery_id,
        "occurred_at": occurred_at,
        "payload": "payload:" + record_id,
    }


def ask(request):
    p = subprocess.run([sys.executable, "main.py"], input=json.dumps(request),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


class Summary(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "summary", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "summary", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_uses_current(self):
        self.assertEqual(ask({"command": "summary", "receipts": []})["protocol"], "1")

    def test_one_delivery_across_accounts_is_one_acceptance(self):
        # Protocol 1: delivery_id alone identifies a delivery across all accounts.
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="B"),
             receipt("R-3", "D-1", "2026-04-01T11:00:00Z", account_id="C")]
        self.assertEqual(ask({"command": "summary", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 2})

    def test_distinct_deliveries_across_accounts(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-2", "2026-04-01T10:00:00Z", account_id="B"),
             receipt("R-3", "D-2", "2026-04-01T12:00:00Z", account_id="A"),
             receipt("R-4", "D-3", "2026-04-01T10:00:00Z", account_id="B")]
        self.assertEqual(ask({"command": "summary", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 3, "duplicate_count": 1})

    def test_offsets_compare_as_utc_across_a_date_boundary(self):
        # 2026-04-02T01:00:00+03:00 is 2026-04-01T22:00:00Z, the earlier instant.
        r = [receipt("R-1", "D-1", "2026-04-01T23:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-02T01:00:00+03:00", account_id="B")]
        self.assertEqual(ask({"command": "summary", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})
