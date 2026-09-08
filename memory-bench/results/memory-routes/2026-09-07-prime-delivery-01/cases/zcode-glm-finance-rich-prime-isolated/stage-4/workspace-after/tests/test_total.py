import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TotalTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def line(self, **overrides):
        line = {
            "line_id": "L-1",
            "account_id": "A",
            "subscription_id": "S",
            "service_on": "2026-04-15",
            "charge_cents": 19999,
        }
        line.update(overrides)
        return line

    def test_empty_statement(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": []},
            {"release": "1.0", "credit_cents": 0, "amount_due_cents": 0},
        )

    def test_issue_example_line(self):
        self.check_request(
            {"command": "total", "release": "1.0", "lines": [self.line()]},
            {"release": "1.0", "credit_cents": 1999, "amount_due_cents": 18000},
        )

    def test_omitted_release_selects_current(self):
        self.check_request(
            {"command": "total", "lines": [self.line()]},
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_release_2_issue_example_line(self):
        self.check_request(
            {"command": "total", "release": "2.0", "lines": [self.line()]},
            {"release": "2.0", "credit_cents": 2999, "amount_due_cents": 17000},
        )

    def test_release_2_cap_shared_within_one_subscription(self):
        lines = [
            self.line(line_id="L-1", charge_cents=10000, service_on="2026-04-01"),
            self.line(line_id="L-2", charge_cents=10000, service_on="2026-04-02"),
            self.line(line_id="L-3", charge_cents=10000, service_on="2026-04-03"),
        ]
        self.check_request(
            {"command": "total", "release": "2.0", "lines": lines},
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 27000},
        )

    def test_release_2_cap_independent_across_subscriptions_of_one_account(self):
        lines = [
            self.line(line_id="L-1", subscription_id="S1", charge_cents=20000),
            self.line(line_id="L-2", subscription_id="S2", charge_cents=20000),
        ]
        self.check_request(
            {"command": "total", "release": "2.0", "lines": lines},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 34000},
        )

    def test_release_2_same_subscription_id_under_different_accounts_independent_caps(self):
        lines = [
            self.line(line_id="L-1", account_id="A", subscription_id="S", charge_cents=30000),
            self.line(line_id="L-2", account_id="B", subscription_id="S", charge_cents=30000),
        ]
        self.check_request(
            {"command": "total", "release": "2.0", "lines": lines},
            {"release": "2.0", "credit_cents": 6000, "amount_due_cents": 54000},
        )

    def test_release_2_largest_charge_first(self):
        lines = [
            self.line(line_id="L-1", charge_cents=100, service_on="2026-04-01"),
            self.line(line_id="L-2", charge_cents=19999, service_on="2026-04-02"),
            self.line(line_id="L-3", charge_cents=10000, service_on="2026-04-03"),
        ]
        self.check_request(
            {"command": "total", "release": "2.0", "lines": lines},
            {"release": "2.0", "credit_cents": 3000, "amount_due_cents": 27099},
        )

    def test_release_2_uncapped_lines_each_round_down(self):
        lines = [self.line(line_id=f"L-{i}", charge_cents=1234) for i in range(3)]
        self.check_request(
            {"command": "total", "release": "2.0", "lines": lines},
            {"release": "2.0", "credit_cents": 555, "amount_due_cents": 3147},
        )

    def test_unsupported_release(self):
        self.check_request(
            {"command": "total", "release": "3.0", "lines": [self.line()]},
            {"error": "unsupported_release"},
        )

    def test_cap_shared_across_subscriptions_of_one_account(self):
        lines = [
            self.line(line_id="L-1", subscription_id="S1", service_on="2026-04-01", charge_cents=10000),
            self.line(line_id="L-2", subscription_id="S2", service_on="2026-04-02", charge_cents=10000),
            self.line(line_id="L-3", subscription_id="S3", service_on="2026-04-03", charge_cents=10000),
        ]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 27600},
        )

    def test_same_subscription_id_under_different_accounts_has_independent_caps(self):
        lines = [
            self.line(line_id="L-1", account_id="A", subscription_id="S", charge_cents=30000),
            self.line(line_id="L-2", account_id="B", subscription_id="S", charge_cents=30000),
        ]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {"release": "1.0", "credit_cents": 4800, "amount_due_cents": 55200},
        )

    def test_equal_service_dates_assign_by_line_id_code_point_order(self):
        lines = [
            self.line(line_id="L-2", service_on="2026-04-15", charge_cents=30000),
            self.line(line_id="L-10", service_on="2026-04-15", charge_cents=30000),
        ]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 57600},
        )

    def test_earliest_service_date_first(self):
        lines = [
            self.line(line_id="L-1", service_on="2026-06-01", charge_cents=30000),
            self.line(line_id="L-9", service_on="2026-05-01", charge_cents=30000),
        ]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {"release": "1.0", "credit_cents": 2400, "amount_due_cents": 57600},
        )

    def test_uncapped_lines_each_round_down(self):
        lines = [self.line(line_id=f"L-{i}", charge_cents=1234) for i in range(3)]
        self.check_request(
            {"command": "total", "release": "1.0", "lines": lines},
            {"release": "1.0", "credit_cents": 369, "amount_due_cents": 3333},
        )

    def test_response_has_exactly_specified_keys(self):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps({"command": "total", "lines": [self.line()]}),
                             text=True, capture_output=True, check=True)
        self.assertEqual(set(json.loads(got.stdout)),
                         {"release", "credit_cents", "amount_due_cents"})
