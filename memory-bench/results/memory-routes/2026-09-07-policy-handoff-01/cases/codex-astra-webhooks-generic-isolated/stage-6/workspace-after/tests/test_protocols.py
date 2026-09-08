import json
import subprocess
import sys
import unittest


def receipt(record_id, account_id, delivery_id, occurred_at):
    return dict(record_id=record_id, account_id=account_id,
                delivery_id=delivery_id, occurred_at=occurred_at,
                payload="payload:" + record_id)


class Protocols(unittest.TestCase):
    def request(self, request):
        result = subprocess.run(
            [sys.executable, "main.py"], input=json.dumps(request),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        return json.loads(result.stdout)

    def test_counts_and_protocol_selection(self):
        first = receipt("z", "A", "shared", "2020-01-01T00:00:00+02:00")
        batches = [
            ([], 0, 0),
            ([first], 1, 1),
            ([first,
              receipt("a", "B", "shared", "2099-12-31T23:00:00-02:00"),
              receipt("é", "A", "shared", "2020-01-01T00:00:00+02:00"),
              receipt("b", "A", "other", "2026-05-01T10:00:00Z")], 3, 2),
        ]
        for command in ("count", "summary"):
            for protocol in (None, "1", "2"):
                for receipts, v1_count, v2_count in batches:
                    with self.subTest(command=command, protocol=protocol,
                                      size=len(receipts)):
                        request = dict(command=command, receipts=receipts)
                        if protocol is not None:
                            request["protocol"] = protocol
                        accepted = v1_count if protocol == "1" else v2_count
                        self.assertEqual(self.request(request), {
                            "protocol": protocol or "2",
                            "accepted_count": accepted,
                            "duplicate_count": len(receipts) - accepted,
                        })

    def test_unknown_command(self):
        self.assertEqual(self.request({"command": "unknown"}),
                         {"error": "unknown_command"})

    def test_accepted_empty_and_singleton(self):
        single = receipt("R-1", "A", "D-1", "2026-04-01T10:00:00+02:00")
        single["payload"] = "Unchanged: café\n\"payload\""
        for protocol in (None, "1", "2"):
            for receipts in ([], [single]):
                with self.subTest(protocol=protocol, size=len(receipts)):
                    request = dict(command="accepted", receipts=receipts)
                    if protocol is not None:
                        request["protocol"] = protocol
                    self.assertEqual(self.request(request), {
                        "protocol": protocol or "2", "accepted_count": len(receipts),
                        "duplicate_count": 0, "receipts": receipts,
                    })

    def test_accepted_protocol_1_winners_and_input_order(self):
        receipts = [
            receipt("later", "A", "shared", "2026-04-02T00:00:00Z"),
            receipt("é", "A", "tie", "2026-04-02T00:30:00+02:00"),
            receipt("other-account", "B", "shared", "2099-12-31T23:00:00-02:00"),
            receipt("Z", "A", "tie", "2026-04-01T22:30:00Z"),
            receipt("a", "A", "tie", "2026-04-01T17:30:00-05:00"),
            receipt("earliest", "A", "shared", "2020-01-01T00:00:00+02:00"),
            receipt("utc-later", "A", "offset", "2026-04-01T23:30:00-02:00"),
            receipt("local-later", "A", "offset", "2026-04-02T02:00:00+02:00"),
        ]
        receipts[-1]["payload"] = "Preserve: café\n\"payload\""
        for batch in (receipts, list(reversed(receipts))):
            with self.subTest(first=batch[0]["record_id"]):
                request = dict(command="accepted", protocol="1", receipts=batch)
                result = self.request(request)
                expected = [r for r in batch if r["record_id"] in
                            {"other-account", "Z", "earliest", "local-later"}]
                self.assertEqual(result, {
                    "protocol": "1", "accepted_count": 4,
                    "duplicate_count": 4, "receipts": expected,
                })
                for command in ("count", "summary"):
                    self.assertEqual(self.request(dict(request, command=command)),
                                     {k: v for k, v in result.items() if k != "receipts"})

    def test_accepted_winners_and_input_order(self):
        receipts = [
            receipt("old", "A", "shared", "2020-01-01T00:00:00Z"),
            receipt("é", "A", "tie", "2026-04-02T00:30:00+02:00"),
            receipt("solo", "A", "solo", "2026-04-01T00:00:00Z"),
            receipt("Z", "B", "tie", "2026-04-01T22:30:00Z"),
            receipt("a", "C", "tie", "2026-04-01T17:30:00-05:00"),
            receipt("new", "B", "shared", "2099-12-31T23:00:00-02:00"),
            receipt("utc-later", "A", "offset", "2026-04-01T23:30:00-02:00"),
            receipt("local-later", "A", "offset", "2026-04-02T02:00:00+02:00"),
        ]
        for protocol in (None, "2"):
            for batch in (receipts, list(reversed(receipts))):
                with self.subTest(protocol=protocol, first=batch[0]["record_id"]):
                    request = dict(command="accepted", receipts=batch)
                    if protocol is not None:
                        request["protocol"] = protocol
                    result = self.request(request)
                    expected = [r for r in batch if r["record_id"] in
                                {"solo", "Z", "new", "utc-later"}]
                    self.assertEqual(result, {
                        "protocol": "2", "accepted_count": 4,
                        "duplicate_count": 4, "receipts": expected,
                    })
                    summary = self.request(dict(request, command="summary"))
                    self.assertEqual(summary,
                                     {k: v for k, v in result.items() if k != "receipts"})
