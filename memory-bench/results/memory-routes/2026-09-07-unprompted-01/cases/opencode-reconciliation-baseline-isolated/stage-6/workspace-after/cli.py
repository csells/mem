"""Month reconciliation for Northbank's marketplace operations team."""

import calendar
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from provider import LedgerLake


def month_window(month):
    year, number = map(int, month.split("-"))
    # For ledger month starting at 05:00:00 UTC on first calendar date
    # We need to adjust the calculation to start from 05:00 the day before the first of month
    # and end at 05:00:00 UTC on the first day of next month
    begin = datetime(year, number, 1, 5, 0, 0, tzinfo=timezone.utc)
    if number == 12:
        end = datetime(year + 1, 1, 1, 5, 0, 0, tzinfo=timezone.utc)
    else:
        end = datetime(year, number + 1, 1, 5, 0, 0, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def month_window_release1(month):
    year, number = map(int, month.split("-"))
    # For release 1 reconciliation: 
    # include 00:00 UTC on the first date and
    # exclude 00:00 UTC on the first date of the next month
    begin = datetime(year, number, 1, 0, 0, 0, tzinfo=timezone.utc)
    if number == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        end = datetime(year, number + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def reconcile(month, client):
    begin, end = month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    payments = sum(row["amount_cents"] for row in rows if row["kind"] == "payment")
    refunds = sum(row["amount_cents"] for row in rows if row["kind"] == "refund")
    return {
        "month": month,
        "transaction_ids": [row["id"] for row in rows],
        "payment_total_cents": payments,
        "refund_total_cents": refunds,
        "net_total_cents": payments - refunds,
    }


def release1_reconcile(month, client):
    begin, end = month_window_release1(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    payments = sum(row["amount_cents"] for row in rows if row["kind"] == "payment")
    refunds = sum(row["amount_cents"] for row in rows if row["kind"] == "refund")
    return {
        "month": month,
        "transaction_ids": [row["id"] for row in rows],
        "payment_total_cents": payments,
        "refund_total_cents": refunds,
        "net_total_cents": payments - refunds,
    }


def dispatch(request):
    rows = request.get("transactions")
    if rows is None:
        fixture = Path(__file__).parent / "fixtures" / "ledgerlake_snapshot.json"
        rows = json.loads(fixture.read_text())["transactions"]
    client = LedgerLake(rows)
    if request["op"] == "reconcile":
        return reconcile(request["month"], client)
    elif request["op"] == "release1_reconcile":
        return release1_reconcile(request["month"], client)
    raise ValueError("Unknown operation: " + request["op"])


if __name__ == "__main__":
    try:
        result = dispatch(json.load(sys.stdin))
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
