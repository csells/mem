#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def handle_notice(account):
    renewal = date.fromisoformat(account["renewal_on"])
    plan_cents = account["plan_cents"]

    if account["completed_years"] >= 3:
        send_on = renewal - timedelta(days=14)
        credit_cents = min(plan_cents * 15 // 100, 3600)
    elif account["autopay"] and account["completed_years"] >= 2:
        send_on = renewal - timedelta(days=21)
        credit_cents = min(plan_cents // 10, 2400)
    else:
        send_on = renewal - timedelta(days=21)
        credit_cents = 0

    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


def csv_field(value):
    s = str(value)
    if any(c in s for c in (',', '"', '\r', '\n')):
        return '"' + s.replace('"', '""') + '"'
    return s


def handle_export(accounts):
    header = "customer_id,send_on,credit_cents,amount_due_cents\n"
    rows = []
    for account in accounts:
        n = handle_notice(account)
        row = ",".join([
            csv_field(n["customer_id"]),
            csv_field(n["send_on"]),
            csv_field(n["credit_cents"]),
            csv_field(n["amount_due_cents"]),
        ]) + "\n"
        rows.append(row)
    return {"csv": header + "".join(rows), "count": len(rows)}


def handle_support_replay(case_id, account):
    # Fixed release 1.0 rules for IOS-1842; must not change with future policy updates.
    renewal = date.fromisoformat(account["renewal_on"])
    send_on = renewal - timedelta(days=21)
    plan_cents = account["plan_cents"]
    if account["autopay"] and account["completed_years"] >= 2:
        credit_cents = min(plan_cents // 10, 2400)
    else:
        credit_cents = 0
    notice = {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }
    return {"case_id": case_id, "notice": notice}


def handle_batch(on, accounts):
    notices = []
    for account in accounts:
        notice = handle_notice(account)
        if notice["send_on"] == on:
            notices.append(notice)
    return {
        "on": on,
        "notices": notices,
        "total_due_cents": sum(n["amount_due_cents"] for n in notices),
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return handle_notice(request["account"])
    if request.get("command") == "export":
        return handle_export(request["accounts"])
    if request.get("command") == "support_replay":
        return handle_support_replay(request["case_id"], request["account"])
    if request.get("command") == "batch":
        return handle_batch(request["on"], request["accounts"])
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
