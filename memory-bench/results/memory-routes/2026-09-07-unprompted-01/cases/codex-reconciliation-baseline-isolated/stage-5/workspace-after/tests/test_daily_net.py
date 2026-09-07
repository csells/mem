import json
from pathlib import Path
import subprocess
import sys
import unittest


class DailyNetTests(unittest.TestCase):
    def request(self, month="2025-02", op="daily_net", **kwargs):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "cli.py")],
            input=json.dumps({"op": op, "month": month, **kwargs}),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def day(self, date, payments, refunds):
        return dict(date=date, payment_total_cents=payments,
                    refund_total_cents=refunds, net_total_cents=payments - refunds)

    def test_bundled_fixture_and_monthly_totals(self):
        report = self.request()
        self.assertEqual(report, {"month": "2025-02", "days": [
            self.day("2025-02-10", 12000, 0),
            self.day("2025-02-27", 2500, 0),
            self.day("2025-02-28", 9700, 400),
        ]})
        close = self.request(op="reconcile")
        for field in ("payment_total_cents", "refund_total_cents", "net_total_cents"):
            self.assertEqual(sum(day[field] for day in report["days"]), close[field])

    def test_cutoffs_offsets_and_calendar_rollovers(self):
        for month, last_day, next_month in [
            ("2000-01", "31", "2000-02"),
            ("2024-02", "29", "2024-03"),
            ("2025-02", "28", "2025-03"),
            ("2025-04", "30", "2025-05"),
            ("2099-12", "31", "2100-01"),
        ]:
            with self.subTest(month=month):
                rows = [
                    ("next", "payment", f"{next_month}-01T05:00:00Z", 9000),
                    ("last", "refund", f"{next_month}-01T05:59:59.999+01:00", 40),
                    ("before", "payment", f"{month}-01T04:59:59.999Z", 8000),
                    ("first", "payment", f"{month}-01T06:00:00+01:00", 100),
                    ("next-day", "refund", f"{month}-02T05:00:00Z", 50),
                    ("first-day-end", "payment", f"{month}-01T22:59:59.999-06:00", 200),
                    ("offset-next", "refund", f"{month}-{last_day}T23:00:00-06:00", 7000),
                ]
                transactions = [dict(id=id_, kind=kind, posted_at=posted,
                                     amount_cents=amount)
                                for id_, kind, posted, amount in rows]
                report = self.request(month, transactions=transactions)
                self.assertEqual(report, {"month": month, "days": [
                    self.day(f"{month}-01", 300, 0),
                    self.day(f"{month}-02", 0, 50),
                    self.day(f"{month}-{last_day}", 0, 40),
                ]})
                close = self.request(month, op="reconcile", transactions=transactions)
                for field in ("payment_total_cents", "refund_total_cents", "net_total_cents"):
                    self.assertEqual(sum(day[field] for day in report["days"]), close[field])

    def test_zero_net_and_zero_amount_days_remain(self):
        rows = [
            ("zero-refund", "refund", "2025-02-20T12:00:00Z", 0),
            ("refund", "refund", "2025-02-11T04:30:00Z", 250),
            ("zero-payment", "payment", "2025-02-15T12:00:00Z", 0),
            ("payment", "payment", "2025-02-10T23:00:00Z", 250),
        ]
        transactions = [dict(id=id_, kind=kind, posted_at=posted, amount_cents=amount)
                        for id_, kind, posted, amount in rows]
        self.assertEqual(self.request(transactions=transactions), {
            "month": "2025-02", "days": [
                self.day("2025-02-10", 250, 250),
                self.day("2025-02-15", 0, 0),
                self.day("2025-02-20", 0, 0),
            ],
        })

    def test_empty_month(self):
        for kwargs in ({"transactions": []}, {"transactions": [{
            "id": "outside", "kind": "payment",
            "posted_at": "2025-03-01T05:00:00Z", "amount_cents": 100,
        }]}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.request(**kwargs), {"month": "2025-02", "days": []})
        self.assertEqual(self.request("2026-01"), {"month": "2026-01", "days": []})


if __name__ == "__main__":
    unittest.main()
