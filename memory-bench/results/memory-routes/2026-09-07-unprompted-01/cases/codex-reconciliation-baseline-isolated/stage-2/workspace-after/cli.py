"""Month reconciliation for Northbank's marketplace operations team."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from provider import LedgerLake


def month_window(month):
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    # The provider's upper bound is exclusive: use the start of the next month.
    if number == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, number + 1, 1, tzinfo=timezone.utc)
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


def csv_field(value):
    value = str(value)
    if any(character in value for character in ',"\r\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def refunds_csv(month, client):
    lines = ["id,posted_at,amount_cents"]
    for row in month_transactions(month, client):
        if row["kind"] == "refund":
            lines.append(",".join(csv_field(row[key]) for key in
                                  ("id", "posted_at", "amount_cents")))
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
