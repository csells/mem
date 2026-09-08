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


class Count(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": []}),
                         {"protocol": "1", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 0})

    def test_omitted_protocol_uses_current(self):
        self.assertEqual(ask({"command": "count", "receipts": []})["protocol"], "2")

    def test_duplicates_of_one_delivery(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
             receipt("R-3", "D-2", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 2, "duplicate_count": 1})

    def test_same_delivery_under_two_accounts_is_a_duplicate(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B")]
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})

    def test_offsets_compare_as_utc_across_a_date_boundary(self):
        # 2026-04-02T01:00:00+03:00 is 2026-04-01T22:00:00Z, the earlier instant.
        r = [receipt("R-1", "D-1", "2026-04-01T23:00:00Z"),
             receipt("R-2", "D-1", "2026-04-02T01:00:00+03:00")]
        self.assertEqual(ask({"command": "count", "protocol": "1", "receipts": r}),
                         {"protocol": "1", "accepted_count": 1, "duplicate_count": 1})


class CountProtocol2(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0})

    def test_single(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0})

    def test_duplicates_of_one_delivery(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
             receipt("R-3", "D-2", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 2, "duplicate_count": 1})

    def test_same_delivery_under_two_accounts_is_two_deliveries(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="B")]
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 2, "duplicate_count": 0})

    def test_applies_to_receipts_of_any_date(self):
        r = [receipt("R-1", "D-1", "2020-01-01T00:00:00Z"),
             receipt("R-2", "D-1", "2099-12-31T23:00:00Z")]
        self.assertEqual(ask({"command": "count", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1})


class Accepted(unittest.TestCase):
    """The accepted receipt itself, per the protocol 1 selection rules."""

    def setUp(self):
        sys.path.insert(0, ".")
        import main
        self.main = main

    def select(self, receipts):
        return self.main.accepted_receipts(receipts, self.main.identity_1, self.main.rank_1)

    def test_earliest_instant_wins(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-2"])

    def test_equal_instants_use_smallest_record_id(self):
        r = [receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-1", "D-1", "2026-04-01T12:00:00+02:00")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-1"])

    def test_accepted_keep_original_input_order(self):
        r = [receipt("R-1", "D-2", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
             receipt("R-3", "D-2", "2026-04-01T08:00:00Z")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-2", "R-3"])


class Accepted2(unittest.TestCase):
    """The accepted receipt itself, per the protocol 2 selection rules."""

    def setUp(self):
        sys.path.insert(0, ".")
        import main
        self.main = main

    def select(self, receipts):
        return self.main.accepted_receipts(receipts, self.main.identity_2, self.main.rank_2)

    def test_latest_instant_wins(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-1"])

    def test_equal_instants_use_smallest_record_id(self):
        r = [receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-1", "D-1", "2026-04-01T12:00:00+02:00")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-1"])

    def test_offsets_compare_as_utc_across_a_date_boundary(self):
        # 2026-04-02T01:00:00+03:00 is 2026-04-01T22:00:00Z, the earlier instant.
        r = [receipt("R-1", "D-1", "2026-04-01T23:00:00Z"),
             receipt("R-2", "D-1", "2026-04-02T01:00:00+03:00")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-1"])

    def test_accounts_separate_deliveries_sharing_a_delivery_id(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T11:00:00Z", account_id="B"),
             receipt("R-3", "D-1", "2026-04-01T12:00:00Z", account_id="A")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-2", "R-3"])

    def test_accepted_keep_original_input_order(self):
        r = [receipt("R-1", "D-2", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z"),
             receipt("R-3", "D-2", "2026-04-01T11:00:00Z")]
        self.assertEqual([a["record_id"] for a in self.select(r)], ["R-2", "R-3"])

    def test_accepted_retains_original_fields_and_timestamp_spelling(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T14:00:00+02:00")]
        self.assertEqual(self.select(r), [r[1]])
