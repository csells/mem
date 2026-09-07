"""Month reconciliation for Northbank's marketplace operations team."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from provider import LedgerLake, parse_timestamp
from incident_replay import incident_replay


def month_window(month):
    """Active ledger months use a fixed 05:00 UTC cutoff in every year."""
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, 5, tzinfo=timezone.utc)
    # LedgerLake excludes the upper bound, so use the start of the next month.
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    end = datetime(next_year, next_month, 1, 5, tzinfo=timezone.utc)
    return begin.isoformat(), end.isoformat()


def month_transactions(month, client):
    begin, end = month_window(month)
    return client.list_transactions(created_from=begin, created_to=end)


def reconcile(month, client):
    rows = month_transactions(month, client)
    payments = sum(row["amount_cents"] for row in rows if row["kind"] == "payment")
    refunds = sum(row["amount_cents"] for row in rows if row["kind"] == "refund")
    return {
        "month": month,
        "transaction_ids": [row["id"] for row in rows],
        "payment_total_cents": payments,
        "refund_total_cents": refunds,
        "net_total_cents": payments - refunds,
    }


def daily_net(month, client):
    days = {}
    for row in month_transactions(month, client):
        posted_at = parse_timestamp(row["posted_at"]).astimezone(timezone.utc)
        date = (posted_at - timedelta(hours=5)).date().isoformat()
        if date not in days:
            days[date] = {
                "date": date,
                "payment_total_cents": 0,
                "refund_total_cents": 0,
                "net_total_cents": 0,
            }
        day = days[date]
        day[row["kind"] + "_total_cents"] += row["amount_cents"]
        day["net_total_cents"] = day["payment_total_cents"] - day["refund_total_cents"]
    return {"month": month, "days": [days[date] for date in sorted(days)]}


def csv_field(value):
    value = str(value)
    if any(character in value for character in ',"\r\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def refunds_csv(month, client):
    lines = ["id,posted_at,amount_cents"]
    for row in month_transactions(month, client):
        if row["kind"] == "refund":
            lines.append(",".join(csv_field(row[field]) for field in
                                  ("id", "posted_at", "amount_cents")))
    return {"month": month, "csv": "\n".join(lines) + "\n"}


def dispatch(request):
    rows = request.get("transactions")
    if rows is None:
        fixture = Path(__file__).parent / "fixtures" / "ledgerlake_snapshot.json"
        rows = json.loads(fixture.read_text())["transactions"]
    if request["op"] == "incident_replay":
        return incident_replay(request["month"], rows)
    client = LedgerLake(rows)
    if request["op"] == "reconcile":
        return reconcile(request["month"], client)
    if request["op"] == "refunds_csv":
        return refunds_csv(request["month"], client)
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
