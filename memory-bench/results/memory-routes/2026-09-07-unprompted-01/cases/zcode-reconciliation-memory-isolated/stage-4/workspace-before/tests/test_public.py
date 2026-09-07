import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider import LedgerLake


class PublicTests(unittest.TestCase):
    def test_midmonth_reconciliation(self):
        request = {"op": "reconcile", "month": "2025-02", "transactions": [
            {"id": "p", "kind": "payment", "posted_at": "2025-02-12T00:00:00Z", "amount_cents": 1250},
            {"id": "r", "kind": "refund", "posted_at": "2025-02-13T00:00:00Z", "amount_cents": 250},
        ]}
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        self.assertEqual(json.loads(result.stdout), {
            "month": "2025-02", "transaction_ids": ["p", "r"],
            "payment_total_cents": 1250, "refund_total_cents": 250, "net_total_cents": 1000,
        })

    def test_provider_time_range(self):
        rows = [{"id": "edge", "kind": "payment", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 1}]
        client = LedgerLake(rows)
        self.assertEqual(client.list_transactions(created_from="2025-02-01T00:00:00Z",
                                                  created_to="2025-03-01T00:00:00Z"), [])


class MonthWindowRegressionTests(unittest.TestCase):
    def run_cli(self, request):
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        return json.loads(result.stdout)

    def test_february_close_includes_last_day(self):
        result = self.run_cli({"op": "reconcile", "month": "2025-02"})
        self.assertEqual(result, {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200,
            "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_thirty_day_month_includes_last_day(self):
        request = {"op": "reconcile", "month": "2025-04", "transactions": [
            {"id": "p-last", "kind": "payment", "posted_at": "2025-04-30T23:59:59Z", "amount_cents": 300},
            {"id": "p-open", "kind": "payment", "posted_at": "2025-05-01T00:00:00Z", "amount_cents": 999},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-04", "transaction_ids": ["p-last"],
            "payment_total_cents": 300, "refund_total_cents": 0, "net_total_cents": 300,
        })

    def test_december_rolls_over_to_january(self):
        request = {"op": "reconcile", "month": "2025-12", "transactions": [
            {"id": "p-new-year-eve", "kind": "payment", "posted_at": "2025-12-31T23:59:59Z", "amount_cents": 500},
            {"id": "p-jan", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 999},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-12", "transaction_ids": ["p-new-year-eve"],
            "payment_total_cents": 500, "refund_total_cents": 0, "net_total_cents": 500,
        })

    def test_first_instant_of_month_is_included(self):
        request = {"op": "reconcile", "month": "2025-03", "transactions": [
            {"id": "p-open", "kind": "payment", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 700},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-03", "transaction_ids": ["p-open"],
            "payment_total_cents": 700, "refund_total_cents": 0, "net_total_cents": 700,
        })


class RefundsCsvTests(unittest.TestCase):
    def run_cli(self, request):
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        return json.loads(result.stdout)

    def test_fixture_february_refund_detail(self):
        result = self.run_cli({"op": "refunds_csv", "month": "2025-02"})
        self.assertEqual(result, {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n",
        })

    def test_month_without_refunds_is_header_only(self):
        result = self.run_cli({"op": "refunds_csv", "month": "2025-03", "transactions": [
            {"id": "p", "kind": "payment", "posted_at": "2025-03-02T00:00:00Z", "amount_cents": 100},
        ]})
        self.assertEqual(result, {"month": "2025-03", "csv": "id,posted_at,amount_cents\n"})

    def test_only_refunds_in_reconcile_order(self):
        result = self.run_cli({"op": "refunds_csv", "month": "2025-02", "transactions": [
            {"id": "p-1", "kind": "payment", "posted_at": "2025-02-12T00:00:00Z", "amount_cents": 500},
            {"id": "r-b", "kind": "refund", "posted_at": "2025-02-13T00:00:00Z", "amount_cents": 250},
            {"id": "r-a", "kind": "refund", "posted_at": "2025-02-13T00:00:00Z", "amount_cents": 150},
            {"id": "r-next", "kind": "refund", "posted_at": "2025-03-01T00:00:00Z", "amount_cents": 999},
        ]})
        self.assertEqual(result, {
            "month": "2025-02",
            "csv": "id,posted_at,amount_cents\n"
                   "r-a,2025-02-13T00:00:00Z,150\n"
                   "r-b,2025-02-13T00:00:00Z,250\n",
        })

    def test_quoting_covers_comma_quote_cr_lf(self):
        result = self.run_cli({"op": "refunds_csv", "month": "2025-02", "transactions": [
            {"id": 'has,comma', "kind": "refund", "posted_at": "2025-02-01T00:00:00Z", "amount_cents": 1},
            {"id": 'has"quote', "kind": "refund", "posted_at": "2025-02-02T00:00:00Z", "amount_cents": 2},
            {"id": "has\rcr", "kind": "refund", "posted_at": "2025-02-03T00:00:00Z", "amount_cents": 3},
            {"id": "has\nlf", "kind": "refund", "posted_at": "2025-02-04T00:00:00Z", "amount_cents": 4},
        ]})
        self.assertEqual(result["csv"],
                         'id,posted_at,amount_cents\n'
                         '"has,comma",2025-02-01T00:00:00Z,1\n'
                         '"has""quote",2025-02-02T00:00:00Z,2\n'
                         '"has\rcr",2025-02-03T00:00:00Z,3\n'
                         '"has\nlf",2025-02-04T00:00:00Z,4\n')

    def test_posted_at_string_preserved(self):
        result = self.run_cli({"op": "refunds_csv", "month": "2025-02", "transactions": [
            {"id": "r", "kind": "refund", "posted_at": "2025-02-28T23:45:00+01:00", "amount_cents": 400},
        ]})
        self.assertEqual(result["csv"],
                         "id,posted_at,amount_cents\nr,2025-02-28T23:45:00+01:00,400\n")


class IncidentReplayTests(unittest.TestCase):
    def run_cli(self, request):
        result = subprocess.run([sys.executable, "cli.py"], input=json.dumps(request), text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], check=True)
        return json.loads(result.stdout)

    def test_fixture_february_matches_corrected_statement(self):
        result = self.run_cli({"op": "incident_replay", "month": "2025-02"})
        self.assertEqual(result, {
            "month": "2025-02",
            "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
            "payment_total_cents": 15200,
            "refund_total_cents": 400,
            "net_total_cents": 14800,
        })

    def test_transactions_override(self):
        request = {"op": "incident_replay", "month": "2025-02", "transactions": [
            {"id": "p", "kind": "payment", "posted_at": "2025-02-12T00:00:00Z", "amount_cents": 1250},
            {"id": "r", "kind": "refund", "posted_at": "2025-02-13T00:00:00Z", "amount_cents": 250},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-02", "transaction_ids": ["p", "r"],
            "payment_total_cents": 1250, "refund_total_cents": 250, "net_total_cents": 1000,
        })

    def test_empty_override_is_empty_month(self):
        result = self.run_cli({"op": "incident_replay", "month": "2025-02", "transactions": []})
        self.assertEqual(result, {
            "month": "2025-02", "transaction_ids": [],
            "payment_total_cents": 0, "refund_total_cents": 0, "net_total_cents": 0,
        })

    def test_december_upper_cutoff_is_january_first(self):
        request = {"op": "incident_replay", "month": "2025-12", "transactions": [
            {"id": "p-eve", "kind": "payment", "posted_at": "2025-12-31T23:59:59Z", "amount_cents": 500},
            {"id": "p-jan", "kind": "payment", "posted_at": "2026-01-01T00:00:00Z", "amount_cents": 999},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-12", "transaction_ids": ["p-eve"],
            "payment_total_cents": 500, "refund_total_cents": 0, "net_total_cents": 500,
        })

    def test_offset_timestamps_compare_as_absolute_instants(self):
        request = {"op": "incident_replay", "month": "2025-02", "transactions": [
            {"id": "p-in", "kind": "payment", "posted_at": "2025-03-01T00:45:00+01:00", "amount_cents": 700},
            {"id": "p-out", "kind": "payment", "posted_at": "2025-02-28T23:30:00-01:00", "amount_cents": 999},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-02", "transaction_ids": ["p-in"],
            "payment_total_cents": 700, "refund_total_cents": 0, "net_total_cents": 700,
        })

    def test_last_instant_of_month_is_included(self):
        request = {"op": "incident_replay", "month": "2025-04", "transactions": [
            {"id": "p-last", "kind": "payment", "posted_at": "2025-04-30T23:59:59Z", "amount_cents": 300},
            {"id": "p-open", "kind": "payment", "posted_at": "2025-05-01T00:00:00Z", "amount_cents": 999},
        ]}
        self.assertEqual(self.run_cli(request), {
            "month": "2025-04", "transaction_ids": ["p-last"],
            "payment_total_cents": 300, "refund_total_cents": 0, "net_total_cents": 300,
        })


if __name__ == "__main__":
    unittest.main()
