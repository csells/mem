"""Frozen corrected release-1 statement rules for incident INC-204.

Keep these rules independent of active accounting reports and their helpers.
"""

from datetime import datetime, timezone


def incident_replay(month, transactions):
    year, number = map(int, month.split("-"))
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)

    postings = []
    for row in transactions:
        instant = datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00"))
        instant = instant.astimezone(timezone.utc)
        if begin <= instant < end:
            postings.append((instant, row))
    postings.sort(key=lambda posting: (posting[0], posting[1]["id"]))

    payments = sum(row["amount_cents"] for _, row in postings
                   if row["kind"] == "payment")
    refunds = sum(row["amount_cents"] for _, row in postings
                  if row["kind"] == "refund")
    return {
        "month": month,
        "transaction_ids": [row["id"] for _, row in postings],
        "payment_total_cents": payments,
        "refund_total_cents": refunds,
        "net_total_cents": payments - refunds,
    }
