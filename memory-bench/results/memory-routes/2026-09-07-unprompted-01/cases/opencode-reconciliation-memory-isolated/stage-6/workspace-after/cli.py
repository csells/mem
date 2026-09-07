"""Month reconciliation for Northbank's marketplace operations team."""

import calendar
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import csv
from io import StringIO

from provider import LedgerLake, parse_timestamp


def month_window(month):
    year, number = map(int, month.split("-"))
    last_day = calendar.monthrange(year, number)[1]
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    # End should include all time up to but not including the start of next month
    end = datetime(year, number, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def release1_month_window(month):
    """Release 1 window: include 00:00 UTC on the first date and every later posting in that UTC month;
    exclude 00:00 UTC on the first date of the next month"""
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    
    # Next month calculation
    if number == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = number + 1
    
    # For release 1, we include all postings from the start of the month UTC through 
    # to but not including the beginning of next month UTC
    end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)
    
    return begin.isoformat(), end.isoformat()


def incident_month_window(month):
    """Calculate correct window for incident replay: from start of month to start of next month"""
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    
    # Next month calculation
    if number == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = number + 1
    
    end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)
    
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
    """Reproduce release 1's complete UTC calendar-month reconciliation behavior"""
    begin, end = release1_month_window(month)
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


def incident_replay(month, client):
    """Reproduce the corrected reconciliation behavior for incident replay"""
    begin, end = incident_month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    
    # Filter for only payment and refund transactions that fall within the month
    # Sort by posting instant then lexicographically by ID
    filtered_rows = sorted(rows, key=lambda row: (parse_timestamp(row["posted_at"]), row["id"]))
    
    payments = sum(row["amount_cents"] for row in filtered_rows if row["kind"] == "payment")
    refunds = sum(row["amount_cents"] for row in filtered_rows if row["kind"] == "refund")
    
    return {
        "month": month,
        "transaction_ids": [row["id"] for row in filtered_rows],
        "payment_total_cents": payments,
        "refund_total_cents": refunds,
        "net_total_cents": payments - refunds,
    }


def refunds_csv(month, client):
    begin, end = month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    # Filter for refunds only and sort by posted_at, then id
    refunds = [row for row in rows if row["kind"] == "refund"]
    refunds.sort(key=lambda x: (x["posted_at"], x["id"]))
    
    # Create CSV string
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
    writer.writerow(["id", "posted_at", "amount_cents"])
    
    for row in refunds:
        writer.writerow([row["id"], row["posted_at"], row["amount_cents"]])
    
    csv_string = output.getvalue()
    if not csv_string.endswith("\n"):
        csv_string += "\n"
    
    return {
        "month": month,
        "csv": csv_string
    }


def dispatch(request):
    rows = request.get("transactions")
    if rows is None:
        fixture = Path(__file__).parent / "fixtures" / "ledgerlake_snapshot.json"
        rows = json.loads(fixture.read_text())["transactions"]
    client = LedgerLake(rows)
    if request["op"] == "reconcile":
        return reconcile(request["month"], client)
    elif request["op"] == "incident_replay":
        return incident_replay(request["month"], client)
    elif request["op"] == "refunds_csv":
        return refunds_csv(request["month"], client)
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
