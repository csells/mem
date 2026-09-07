import json
from pathlib import Path
import subprocess
import sys
import unittest


class IncidentReplayTests(unittest.TestCase):
    def replay(self, month, **kwargs):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "cli.py")],
            input=json.dumps({"op": "incident_replay", "month": month, **kwargs}),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_incident_statement(self):
        self.assertEqual(self.replay("2025-02"), {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200, "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_utc_calendar_boundaries_and_order(self):
        for month, last_day, next_month in [
            ("2025-02", "28", "2025-03"),
            ("2024-02", "29", "2024-03"),
            ("2025-04", "30", "2025-05"),
            ("2025-01", "31", "2025-02"),
            ("2025-12", "31", "2026-01"),
            ("2099-12", "31", "2100-01"),
        ]:
            with self.subTest(month=month):
                rows = [
                    ("next", "payment", f"{next_month}-01T00:00:00Z", 9000),
                    ("z-last", "refund", f"{month}-{last_day}T23:59:59.999Z", 700),
                    ("before", "payment", f"{month}-01T00:59:59.999+01:00", 8000),
                    ("a-last", "payment", f"{next_month}-01T00:59:59.999+01:00", 300),
                    ("first", "payment", f"{month}-01T01:00:00+01:00", 100),
                    ("last-midnight", "payment", f"{month}-{last_day}T00:00:00Z", 200),
                    ("offset-next", "refund", f"{month}-{last_day}T23:00:00-01:00", 7000),
                    ("negative-offset", "refund", f"{month}-01T00:00:00-01:00", 0),
                ]
                transactions = [
                    dict(id=id_, kind=kind, posted_at=timestamp, amount_cents=amount)
                    for id_, kind, timestamp, amount in rows
                ]
                self.assertEqual(self.replay(month, transactions=transactions), {
                    "month": month,
                    "transaction_ids": ["first", "negative-offset", "last-midnight",
                                        "a-last", "z-last"],
                    "payment_total_cents": 600, "refund_total_cents": 700,
                    "net_total_cents": -100,
                })

    def test_empty_override(self):
        self.assertEqual(self.replay("2025-02", transactions=[]), {
            "month": "2025-02", "transaction_ids": [],
            "payment_total_cents": 0, "refund_total_cents": 0, "net_total_cents": 0,
        })


if __name__ == "__main__":
    unittest.main()
