"""Month reconciliation for Northbank's marketplace operations team."""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

from provider import LedgerLake


def month_window(month):
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    end = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=timezone.utc)
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


def csv_field(value):
    text = str(value)
    if any(character in text for character in (",", '"', "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def refunds_csv(month, client):
    begin, end = month_window(month)
    rows = client.list_transactions(created_from=begin, created_to=end)
    lines = ["id,posted_at,amount_cents"]
    for row in rows:
        if row["kind"] == "refund":
            lines.append(",".join([
                csv_field(row["id"]),
                csv_field(row["posted_at"]),
                csv_field(row["amount_cents"]),
            ]))
    return {"month": month, "csv": "\n".join(lines) + "\n"}


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
    raise ValueError("Unknown operation: " + request["op"])


if __name__ == "__main__":
    try:
        result = dispatch(json.load(sys.stdin))
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
