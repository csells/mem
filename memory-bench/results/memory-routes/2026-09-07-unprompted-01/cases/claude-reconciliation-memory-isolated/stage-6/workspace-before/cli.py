"""Month reconciliation for Northbank's marketplace operations team."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from provider import LedgerLake


def month_window(month):
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def active_month_window(month):
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, 5, 0, 0, tzinfo=timezone.utc)
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    end = datetime(next_year, next_month, 1, 5, 0, 0, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def reconcile(month, client):
    begin, end = active_month_window(month)
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


def csv_field(value):
    s = str(value)
    if any(c in s for c in (',', '"', '\r', '\n')):
        return '"' + s.replace('"', '""') + '"'
    return s


def refunds_csv(month, client):
    begin, end = active_month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    refunds = [row for row in rows if row["kind"] == "refund"]
    lines = ["id,posted_at,amount_cents\n"]
    for row in refunds:
        fields = [csv_field(row["id"]), csv_field(row["posted_at"]), csv_field(row["amount_cents"])]
        lines.append(",".join(fields) + "\n")
    return {"month": month, "csv": "".join(lines)}


def incident_replay(month, client):
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


def ledger_day_date(posted_at_str):
    ts = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    return (ts - timedelta(hours=5)).date().isoformat()


def daily_net(month, client):
    begin, end = active_month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    days = {}
    for row in rows:
        date = ledger_day_date(row["posted_at"])
        if date not in days:
            days[date] = {"payment_total_cents": 0, "refund_total_cents": 0}
        if row["kind"] == "payment":
            days[date]["payment_total_cents"] += row["amount_cents"]
        else:
            days[date]["refund_total_cents"] += row["amount_cents"]
    result_days = [
        {
            "date": date,
            "payment_total_cents": totals["payment_total_cents"],
            "refund_total_cents": totals["refund_total_cents"],
            "net_total_cents": totals["payment_total_cents"] - totals["refund_total_cents"],
        }
        for date, totals in sorted(days.items())
    ]
    return {"month": month, "days": result_days}


def dispatch(request):
    rows = request.get("transactions")
    if rows is None:
        fixture = Path(__file__).parent / "fixtures" / "ledgerlake_snapshot.json"
        rows = json.loads(fixture.read_text())["transactions"]
    client = LedgerLake(rows)
    if request["op"] == "reconcile":
        return reconcile(request["month"], client)
    if request["op"] == "refunds_csv":
        return refunds_csv(request["month"], client)
    if request["op"] == "incident_replay":
        return incident_replay(request["month"], client)
    if request["op"] == "daily_net":
        return daily_net(request["month"], client)
    raise ValueError("Unknown operation: " + request["op"])


if __name__ == "__main__":
    try:
        result = dispatch(json.load(sys.stdin))
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
