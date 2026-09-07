#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def handle_notice(account):
    renewal_on = date.fromisoformat(account["renewal_on"])
    send_on = renewal_on - timedelta(days=21)
    plan_cents = account["plan_cents"]
    if account["autopay"] and account["completed_years"] >= 2:
        credit_cents = min(plan_cents // 10, 2400)
    else:
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
    lines = header
    for account in accounts:
        notice = handle_notice(account)
        fields = [notice["customer_id"], notice["send_on"],
                  notice["credit_cents"], notice["amount_due_cents"]]
        lines += ",".join(csv_field(f) for f in fields) + "\n"
    return {"csv": lines, "count": len(accounts)}


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return handle_notice(request["account"])
    if request.get("command") == "export":
        return handle_export(request["accounts"])
    if request.get("command") == "support_replay":
        return {"case_id": request["case_id"], "notice": handle_notice(request["account"])}
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
