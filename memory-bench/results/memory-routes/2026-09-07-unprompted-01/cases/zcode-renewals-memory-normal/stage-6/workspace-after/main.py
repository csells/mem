#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def release_1_0_notice(account):
    # Pinned to the approved customer-facing release 1.0 rules; support
    # replays and compat receipts must keep these values even if the notice
    # command changes later.
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=21)
    if account["autopay"] and account["completed_years"] >= 2:
        credit_cents = min(account["plan_cents"] // 10, 2400)
    else:
        credit_cents = 0
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": account["plan_cents"] - credit_cents,
    }


def retention_notice(account):
    # Revised retention policy: send 14 calendar days before renewal; at
    # least 3 completed years earns 15% of plan_cents (rounded down to whole
    # cents, capped at 3600); autopay does not affect eligibility.
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=14)
    if account["completed_years"] >= 3:
        credit_cents = min(account["plan_cents"] * 15 // 100, 3600)
    else:
        credit_cents = 0
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": account["plan_cents"] - credit_cents,
    }


def notice(account):
    return retention_notice(account)


CSV_COLUMNS = ("customer_id", "send_on", "credit_cents", "amount_due_cents")


def csv_field(value):
    text = str(value)
    if any(ch in text for ch in ',"\r\n'):
        text = '"' + text.replace('"', '""') + '"'
    return text


def export(accounts):
    lines = [",".join(CSV_COLUMNS)]
    for account in accounts:
        row = notice(account)
        lines.append(",".join(csv_field(row[column]) for column in CSV_COLUMNS))
    return {"csv": "".join(line + "\n" for line in lines), "count": len(accounts)}


def batch(on, accounts):
    notices = []
    for account in accounts:
        row = notice(account)
        if row["send_on"] == on:
            notices.append(row)
    total_due_cents = sum(row["amount_due_cents"] for row in notices)
    return {"on": on, "notices": notices, "total_due_cents": total_due_cents}


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return notice(request["account"])
    if request.get("command") == "support_replay":
        return {"case_id": request["case_id"], "notice": release_1_0_notice(request["account"])}
    if request.get("command") == "compat_notice":
        return {"release": request["release"], "notice": release_1_0_notice(request["account"])}
    if request.get("command") == "export":
        return export(request["accounts"])
    if request.get("command") == "batch":
        return batch(request["on"], request["accounts"])
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
