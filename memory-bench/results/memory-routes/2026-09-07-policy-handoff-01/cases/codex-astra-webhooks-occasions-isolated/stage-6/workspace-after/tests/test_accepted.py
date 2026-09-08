import json
import subprocess
import sys
import unittest


def receipt(record_id, delivery_id, occurred_at, account_id="A"):
    return {"record_id": record_id, "account_id": account_id,
            "delivery_id": delivery_id, "occurred_at": occurred_at,
            "payload": "original payload: " + record_id}


class Accepted(unittest.TestCase):
    def request(self, command, receipts, protocol):
        request = {"command": command, "receipts": receipts}
        if protocol is not None:
            request["protocol"] = protocol
        result = subprocess.run(
            [sys.executable, "main.py"], input=json.dumps(request),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def check_accepted(self, receipts, winner_ids, protocols=(None, "2")):
        for protocol in protocols:
            for ordered in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, receipts=ordered):
                    expected = [r for r in ordered if r["record_id"] in winner_ids]
                    actual = self.request("accepted", ordered, protocol)
                    self.assertEqual(actual, {
                        "protocol": protocol or "2", "accepted_count": len(expected),
                        "duplicate_count": len(ordered) - len(expected),
                        "receipts": expected,
                    })
                    counts = {k: v for k, v in actual.items() if k != "receipts"}
                    self.assertEqual(counts, self.request("summary", ordered, protocol))

    def test_latest_utc_across_accounts_and_date_boundaries(self):
        self.check_accepted([
            receipt("first", "D2", "2026-01-01T00:00:00Z"),
            receipt("a", "D1", "2026-01-02T00:30:00+02:00"),
            receipt("z", "D1", "2026-01-01T23:00:00Z", "B"),
            receipt("last", "D3", "2020-01-01T00:00:00+02:00"),
            receipt("newest", "D3", "2099-12-31T23:00:00-02:00", "B"),
            receipt("older", "D2", "2025-12-31T23:59:59Z"),
        ], {"first", "z", "newest"})

    def test_equal_instants_use_unicode_record_id_order(self):
        self.check_accepted([
            receipt("中", "D1", "2026-01-01T00:30:00+02:00"),
            receipt("é", "D1", "2025-12-31T22:30:00Z", "B"),
            receipt("Z", "D1", "2025-12-31T17:30:00-05:00"),
            receipt("a", "D1", "2025-12-31T22:30:00+00:00", "C"),
        ], {"Z"})

    def test_empty(self):
        self.check_accepted([], set())

    def test_singleton(self):
        self.check_accepted([
            receipt("only", "D", "2026-01-01T00:00:00-08:00"),
        ], {"only"})

    def test_protocol_1_earliest_utc_and_separate_accounts(self):
        self.check_accepted([
            receipt("first", "D2", "2026-01-01T00:00:00Z"),
            receipt("z", "D1", "2026-01-02T00:30:00+02:00"),
            receipt("a", "D1", "2026-01-01T23:00:00Z"),
            receipt("other-account", "D1", "2099-12-31T23:30:00-02:00", "B"),
            receipt("oldest", "D3", "2020-01-01T00:00:00+02:00"),
            receipt("newest", "D3", "2099-12-31T23:00:00-02:00"),
            receipt("older", "D2", "2025-12-31T23:59:59Z"),
        ], {"z", "other-account", "oldest", "older"}, protocols=("1",))

    def test_protocol_1_equal_instants_use_unicode_record_id_order(self):
        self.check_accepted([
            receipt("中", "D1", "2026-01-01T00:30:00+02:00"),
            receipt("é", "D1", "2025-12-31T22:30:00Z"),
            receipt("Z", "D1", "2025-12-31T17:30:00-05:00"),
            receipt("a", "D1", "2025-12-31T22:30:00+00:00"),
            receipt("B", "D1", "2025-12-31T22:30:00Z", "B"),
        ], {"Z", "B"}, protocols=("1",))

    def test_protocol_1_empty(self):
        self.check_accepted([], set(), protocols=("1",))

    def test_protocol_1_singleton(self):
        self.check_accepted([
            receipt("only", "D", "2026-01-01T00:00:00-08:00"),
        ], {"only"}, protocols=("1",))
