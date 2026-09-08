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


class Accepted(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": []}),
                         {"protocol": "2", "accepted_count": 0, "duplicate_count": 0,
                          "receipts": []})

    def test_single_receipt_is_returned_unchanged(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 0,
                          "receipts": r})

    def test_latest_instant_wins_within_an_account(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-2", "D-1", "2026-04-01T12:00:00Z"),
             receipt("R-3", "D-1", "2026-04-01T09:00:00Z")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 2,
                          "receipts": [r[1]]})

    def test_equal_instants_use_the_smallest_record_id(self):
        r = [receipt("R-2", "D-1", "2026-04-01T10:00:00Z"),
             receipt("R-1", "D-1", "2026-04-01T10:00:00Z")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r})["receipts"],
                         [r[1]])

    def test_representatives_keep_original_input_order(self):
        # D-2's winner appears later in the input than D-1's, so it is listed second.
        r = [receipt("R-1", "D-2", "2026-04-01T12:00:00Z", account_id="B"),
             receipt("R-2", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-3", "D-2", "2026-04-01T13:00:00Z", account_id="B")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 2, "duplicate_count": 1,
                          "receipts": [r[1], r[2]]})

    def test_one_delivery_id_across_accounts_is_one_delivery_each(self):
        # Protocol 2: (account_id, delivery_id) identifies a delivery.
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="B"),
             receipt("R-3", "D-1", "2026-04-01T11:00:00Z", account_id="C")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 3, "duplicate_count": 0,
                          "receipts": r})

    def test_offsets_compare_as_utc_across_a_date_boundary(self):
        # 2026-04-02T01:00:00+03:00 is 2026-04-01T22:00:00Z, the earlier instant,
        # so the Z-spelled receipt is accepted with its timestamp spelling intact.
        r = [receipt("R-1", "D-1", "2026-04-01T23:00:00Z"),
             receipt("R-2", "D-1", "2026-04-02T01:00:00+03:00")]
        self.assertEqual(ask({"command": "accepted", "protocol": "2", "receipts": r}),
                         {"protocol": "2", "accepted_count": 1, "duplicate_count": 1,
                          "receipts": [r[0]]})

    def test_omitted_protocol_uses_current(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-1", "2026-04-01T09:00:00Z", account_id="B")]
        self.assertEqual(ask({"command": "accepted", "receipts": r}),
                         ask({"command": "accepted", "protocol": "2", "receipts": r}))

    def test_counts_match_summary_for_the_same_request(self):
        r = [receipt("R-1", "D-1", "2026-04-01T10:00:00Z", account_id="A"),
             receipt("R-2", "D-2", "2026-04-01T10:00:00Z", account_id="B"),
             receipt("R-3", "D-1", "2026-04-01T12:00:00Z", account_id="A"),
             receipt("R-4", "D-2", "2026-04-01T10:00:00Z", account_id="A")]
        got = ask({"command": "accepted", "protocol": "2", "receipts": r})
        summary = ask({"command": "summary", "protocol": "2", "receipts": r})
        self.assertEqual({k: got[k] for k in summary}, summary)
        self.assertEqual(got["accepted_count"], len(got["receipts"]))


if __name__ == "__main__":
    unittest.main()
