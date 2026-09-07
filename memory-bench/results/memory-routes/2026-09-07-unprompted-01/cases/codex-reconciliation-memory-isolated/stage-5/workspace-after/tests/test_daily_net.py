import json
from pathlib import Path
import subprocess
import sys
import unittest


class DailyNetTests(unittest.TestCase):
    def request(self, month, op="daily_net", **kwargs):
        result = subprocess.run(
            [sys.executable, "cli.py"],
            input=json.dumps({"op": op, "month": month, **kwargs}),
            text=True, capture_output=True,
            cwd=Path(__file__).resolve().parents[1], check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def day(self, date, payments, refunds):
        return {"date": date, "payment_total_cents": payments,
                "refund_total_cents": refunds, "net_total_cents": payments - refunds}

    def test_bundled_fixture_and_reconciliation_totals(self):
        actual = self.request("2025-02")
        self.assertEqual(actual, {"month": "2025-02", "days": [
            self.day("2025-02-10", 12000, 0),
            self.day("2025-02-27", 2500, 0),
            self.day("2025-02-28", 9700, 400),
        ]})
        reconciliation = self.request("2025-02", op="reconcile")
        for field in ("payment_total_cents", "refund_total_cents", "net_total_cents"):
            self.assertEqual(sum(day[field] for day in actual["days"]), reconciliation[field])

    def test_month_boundaries_and_calendar_rollovers(self):
        for month, last_day, next_start in [
            ("2000-02", "2000-02-29", "2000-03-01"),
            ("2025-02", "2025-02-28", "2025-03-01"),
            ("2025-04", "2025-04-30", "2025-05-01"),
            ("2025-07", "2025-07-31", "2025-08-01"),
            ("2099-12", "2099-12-31", "2100-01-01"),
        ]:
            with self.subTest(month=month):
                rows = [
                    {"id": "next", "kind": "payment", "posted_at": next_start + "T05:00:00Z", "amount_cents": 900},
                    {"id": "r", "kind": "refund", "posted_at": next_start + "T04:59:59.999Z", "amount_cents": 250},
                    {"id": "p", "kind": "payment", "posted_at": last_day + "T23:00:00Z", "amount_cents": 1000},
                    {"id": "start", "kind": "refund", "posted_at": month + "-01T05:00:00Z", "amount_cents": 10},
                    {"id": "before", "kind": "payment", "posted_at": month + "-01T04:59:59.999Z", "amount_cents": 900},
                ]
                self.assertEqual(self.request(month, transactions=rows), {
                    "month": month, "days": [self.day(month + "-01", 0, 10), self.day(last_day, 1000, 250)],
                })

    def test_daily_cutoff_offsets_and_zero_days(self):
        rows = [
            {"id": "zero", "kind": "payment", "posted_at": "2025-02-15T05:00:00Z", "amount_cents": 0},
            {"id": "next-day", "kind": "refund", "posted_at": "2025-02-13T00:00:00-05:00", "amount_cents": 50},
            {"id": "r", "kind": "refund", "posted_at": "2025-02-13T05:59:59.999+01:00", "amount_cents": 100},
            {"id": "p", "kind": "payment", "posted_at": "2025-02-11T23:00:00-06:00", "amount_cents": 100},
        ]
        self.assertEqual(self.request("2025-02", transactions=rows), {
            "month": "2025-02", "days": [self.day("2025-02-12", 100, 100),
                                           self.day("2025-02-13", 0, 50),
                                           self.day("2025-02-15", 0, 0)],
        })

    def test_empty_months(self):
        self.assertEqual(self.request("2025-02", transactions=[]), {"month": "2025-02", "days": []})
        self.assertEqual(self.request("2020-01"), {"month": "2020-01", "days": []})


if __name__ == "__main__":
    unittest.main()
