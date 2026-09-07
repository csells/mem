#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def make_release_1_0_notice(account):
    """Approved release 1.0 values for compatibility receipts and IOS-1842."""
    credit_cents = 0
    if account["autopay"] and account["completed_years"] >= 2:
        credit_cents = min(account["plan_cents"] // 10, 2400)
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=21)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": account["plan_cents"] - credit_cents,
    }


def make_notice(account):
    """Current customer-facing policy; future changes belong here."""
    credit_cents = 0
    if account["completed_years"] >= 3:
        credit_cents = min(account["plan_cents"] * 15 // 100, 3600)
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=14)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": account["plan_cents"] - credit_cents,
    }


def csv_field(value):
    value = str(value)
    if any(character in value for character in ',"\r\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def export_notices(accounts):
    columns = ("customer_id", "send_on", "credit_cents", "amount_due_cents")
    rows = [",".join(columns)]
    for account in accounts:
        notice = make_notice(account)
        rows.append(",".join(csv_field(notice[column]) for column in columns))
    return {"csv": "\n".join(rows) + "\n", "count": len(accounts)}


def batch_notices(on, accounts):
    notices = []
    for account in accounts:
        notice = make_notice(account)
        if notice["send_on"] == on:
            notices.append(notice)
    return {
        "on": on,
        "notices": notices,
        "total_due_cents": sum(notice["amount_due_cents"] for notice in notices),
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return make_notice(request["account"])
    if request.get("command") == "export":
        return export_notices(request["accounts"])
    if request.get("command") == "batch":
        return batch_notices(request["on"], request["accounts"])
    if request.get("command") == "compat_notice":
        return {
            "release": request["release"],
            "notice": make_release_1_0_notice(request["account"]),
        }
    if request.get("command") == "support_replay":
        return {
            "case_id": request["case_id"],
            "notice": make_release_1_0_notice(request["account"]),
        }
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
