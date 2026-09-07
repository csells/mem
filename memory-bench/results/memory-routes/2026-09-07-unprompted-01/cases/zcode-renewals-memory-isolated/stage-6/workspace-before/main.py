#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
from datetime import date, timedelta
import json
import sys

RETENTION_MIN_YEARS = 3
RETENTION_CAP_CENTS = 3600
NOTICE_LEAD_DAYS = 14

# Frozen release-1.0 policy; kept only for the archived support_replay case.
RELEASE_1_MIN_YEARS = 2
RELEASE_1_CAP_CENTS = 2400
RELEASE_1_LEAD_DAYS = 21


def notice(account):
    plan_cents = account["plan_cents"]
    if account["completed_years"] >= RETENTION_MIN_YEARS:
        credit_cents = min(plan_cents * 15 // 100, RETENTION_CAP_CENTS)
    else:
        credit_cents = 0
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=NOTICE_LEAD_DAYS)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


def release_1_notice(account):
    plan_cents = account["plan_cents"]
    if account["autopay"] and account["completed_years"] >= RELEASE_1_MIN_YEARS:
        credit_cents = min(plan_cents * 10 // 100, RELEASE_1_CAP_CENTS)
    else:
        credit_cents = 0
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=RELEASE_1_LEAD_DAYS)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


EXPORT_COLUMNS = ("customer_id", "send_on", "credit_cents", "amount_due_cents")


def csv_field(value):
    if any(ch in value for ch in (",", '"', "\r", "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def export(accounts):
    lines = [",".join(EXPORT_COLUMNS)]
    for account in accounts:
        row = notice(account)
        lines.append(",".join(csv_field(str(row[column])) for column in EXPORT_COLUMNS))
    return {"csv": "".join(line + "\n" for line in lines), "count": len(accounts)}


def batch(on, accounts):
    notices = []
    total_due_cents = 0
    for account in accounts:
        row = notice(account)
        if row["send_on"] == on:
            notices.append(row)
            total_due_cents += row["amount_due_cents"]
    return {"on": on, "notices": notices, "total_due_cents": total_due_cents}


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return notice(request["account"])
    if request.get("command") == "export":
        return export(request["accounts"])
    if request.get("command") == "batch":
        return batch(request["on"], request["accounts"])
    if request.get("command") == "support_replay":
        return {"case_id": request["case_id"], "notice": release_1_notice(request["account"])}
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
