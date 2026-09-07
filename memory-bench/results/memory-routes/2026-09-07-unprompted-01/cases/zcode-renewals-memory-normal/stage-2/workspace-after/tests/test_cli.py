import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def call(self, request):
        result = subprocess.run([sys.executable, str(ROOT / "main.py")], input=json.dumps(request), capture_output=True, text=True, check=True, timeout=3)
        return json.loads(result.stdout)

    def test_ping(self):
        self.assertEqual(self.call({"command": "ping"}), {"status": "ok", "product": "HarborPass"})

    def test_unknown_command(self):
        self.assertEqual(self.call({"command": "not_a_command"}), {"error": "unknown_command"})

    def test_notice(self):
        self.assertEqual(
            self.call({"command": "notice", "account": {"customer_id": "M-17", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True}}),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_notice_without_autopay_gets_no_credit(self):
        self.assertEqual(
            self.call({"command": "notice", "account": {"customer_id": "M-17", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": False}}),
            {"customer_id": "M-17", "send_on": "2026-03-25", "credit_cents": 0, "amount_due_cents": 19999},
        )

    def test_notice_credit_is_capped(self):
        self.assertEqual(
            self.call({"command": "notice", "account": {"customer_id": "M-9", "renewal_on": "2026-06-01", "plan_cents": 90000, "completed_years": 8, "autopay": True}}),
            {"customer_id": "M-9", "send_on": "2026-05-11", "credit_cents": 2400, "amount_due_cents": 87600},
        )

    def test_export(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": [{"customer_id": "M-17", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True}]}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\nM-17,2026-03-25,1999,18000\n", "count": 1},
        )

    def test_export_empty_collection(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": []}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\n", "count": 0},
        )

    def test_export_preserves_order_and_duplicates(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": [
                {"customer_id": "M-2", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True},
                {"customer_id": "M-1", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True},
                {"customer_id": "M-2", "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True},
            ]}),
            {"csv": "customer_id,send_on,credit_cents,amount_due_cents\nM-2,2026-03-25,1999,18000\nM-1,2026-03-25,1999,18000\nM-2,2026-03-25,1999,18000\n", "count": 3},
        )

    def test_export_quotes_fields_with_commas_or_quotes(self):
        self.assertEqual(
            self.call({"command": "export", "accounts": [{"customer_id": 'Doe, "Jane"\nCo', "renewal_on": "2026-04-15", "plan_cents": 19999, "completed_years": 2, "autopay": True}]}),
            {"csv": 'customer_id,send_on,credit_cents,amount_due_cents\n"Doe, ""Jane""\nCo",2026-03-25,1999,18000\n', "count": 1},
        )


if __name__ == "__main__":
    unittest.main()
