"""Independent oracle: classify postings by ledger-date labels, without provider queries."""

import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys


def posting(row):
    return datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00")).astimezone(timezone.utc)


def totals(rows):
    pay = sum(r["amount_cents"] for r in rows if r["kind"] == "payment")
    refund = sum(r["amount_cents"] for r in rows if r["kind"] == "refund")
    return {"payment_total_cents": pay, "refund_total_cents": refund, "net_total_cents": pay - refund}


def csv_record(values):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerow(values)
    return stream.getvalue()[:-2] + "\n"


def process(request, stage):
    op, month = request["op"], request["month"]
    permitted = {"reconcile"}
    for first_stage, added in [(2, "refunds_csv"), (3, "incident_replay"), (5, "daily_net"), (6, "release1_reconcile")]:
        if stage >= first_stage:
            permitted.add(added)
    if op not in permitted:
        raise ValueError("Unsupported operation " + op)
    all_rows = request.get("transactions")
    if all_rows is None:
        all_rows = json.loads((Path(__file__).parent / "ledgerlake_snapshot.json").read_text())["transactions"]
    shifted = stage >= 4 and op in {"reconcile", "refunds_csv", "daily_net"}
    shift = timedelta(hours=5 if shifted else 0)
    rows = []
    for row in all_rows:
        date = (posting(row) - shift - timedelta(milliseconds=1)).date()
        if date.strftime("%Y-%m") != month:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (posting(row), row["id"]))
    if op == "refunds_csv":
        result = [csv_record(["id", "posted_at", "amount_cents"])]
        for row in rows:
            if row["kind"] == "refund":
                result.append(csv_record([row["id"], row["posted_at"], row["amount_cents"]]))
        return {"month": month, "csv": "".join(result)}
    if op == "daily_net":
        groups = {}
        for row in rows:
            date = (posting(row) - shift - timedelta(milliseconds=1)).date().isoformat()
            groups.setdefault(date, []).append(row)
        return {"month": month, "days": [{"date": date, **totals(group)} for date, group in sorted(groups.items())]}
    return {"month": month, "transaction_ids": [row["id"] for row in rows], **totals(rows)}


def run(stage):
    print(json.dumps(process(json.load(sys.stdin), stage)))
