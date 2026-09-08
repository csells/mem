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
