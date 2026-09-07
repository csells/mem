import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def daily_net(request):
    result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request),
                            text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


class DailyNetTests(unittest.TestCase):
    def test_settlement_day_crosses_midnight_into_next_calendar_month(self):
        rows = [
            {"id": "p", "kind": "payment", "posted_at": "2025-02-28T23:00:00Z", "amount_cents": 1000},
            {"id": "r", "kind": "refund", "posted_at": "2025-03-01T04:30:00Z", "amount_cents": 250},
            {"id": "next", "kind": "payment", "posted_at": "2025-03-01T05:00:00Z", "amount_cents": 900},
        ]
        self.assertEqual(daily_net({"op": "daily_net", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "days": [
                {"date": "2025-02-28", "payment_total_cents": 1000,
                 "refund_total_cents": 250, "net_total_cents": 750},
            ],
        })

    def test_daily_breakdown_from_snapshot(self):
        self.assertEqual(daily_net({"op": "daily_net", "month": "2025-02"}), {
            "month": "2025-02",
            "days": [
                {"date": "2025-02-10", "payment_total_cents": 12000,
                 "refund_total_cents": 0, "net_total_cents": 12000},
                {"date": "2025-02-27", "payment_total_cents": 2500,
                 "refund_total_cents": 0, "net_total_cents": 2500},
                {"date": "2025-02-28", "payment_total_cents": 9700,
                 "refund_total_cents": 400, "net_total_cents": 9300},
            ],
        })

    def test_days_without_transactions_are_omitted_and_zero_net_day_is_kept(self):
        rows = [
            {"id": "a", "kind": "payment", "posted_at": "2025-06-02T05:00:00Z", "amount_cents": 500},
            {"id": "b", "kind": "refund", "posted_at": "2025-06-03T04:59:59.999Z", "amount_cents": 500},
            {"id": "c", "kind": "payment", "posted_at": "2025-06-10T12:00:00Z", "amount_cents": 700},
        ]
        self.assertEqual(daily_net({"op": "daily_net", "month": "2025-06", "transactions": rows}), {
            "month": "2025-06",
            "days": [
                {"date": "2025-06-02", "payment_total_cents": 500,
                 "refund_total_cents": 500, "net_total_cents": 0},
                {"date": "2025-06-10", "payment_total_cents": 700,
                 "refund_total_cents": 0, "net_total_cents": 700},
            ],
        })

    def test_empty_month_returns_no_days(self):
        self.assertEqual(daily_net({"op": "daily_net", "month": "2025-07", "transactions": []}),
                         {"month": "2025-07", "days": []})

    def test_offset_written_timestamp_groups_by_utc_ledger_day(self):
        rows = [
            {"id": "late-jst", "kind": "payment", "posted_at": "2025-02-11T08:30:00+09:00", "amount_cents": 300},
            {"id": "early-jst", "kind": "payment", "posted_at": "2025-02-11T12:30:00+09:00", "amount_cents": 100},
        ]
        self.assertEqual(daily_net({"op": "daily_net", "month": "2025-02", "transactions": rows}), {
            "month": "2025-02",
            "days": [
                {"date": "2025-02-10", "payment_total_cents": 400,
                 "refund_total_cents": 0, "net_total_cents": 400},
            ],
        })


if __name__ == "__main__":
    unittest.main()
