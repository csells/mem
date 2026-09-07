#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def notice(account):
    """Current retention policy, applied regardless of renewal date."""
    plan_cents = account["plan_cents"]
    credit_cents = 0
    if account["completed_years"] >= 3:
        credit_cents = min(plan_cents * 15 // 100, 3600)
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=14)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


def release_1_0_notice(account):
    """Frozen customer-facing policy approved in trial-0fl for release 1.0."""
    plan_cents = account["plan_cents"]
    credit_cents = 0
    if account["autopay"] and account["completed_years"] >= 2:
        credit_cents = min(plan_cents // 10, 2400)
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=21)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


def ios_1842_notice(account):
    """The archived IOS-1842 preview matches the approved release 1.0 policy."""
    return release_1_0_notice(account)


def csv_field(value):
    text = str(value)
    if any(character in text for character in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def export_notices(accounts):
    columns = ("customer_id", "send_on", "credit_cents", "amount_due_cents")
    rows = [",".join(columns)]
    for account in accounts:
        account_notice = notice(account)
        rows.append(",".join(csv_field(account_notice[column]) for column in columns))
    return {"csv": "\n".join(rows) + "\n", "count": len(accounts)}


def batch_notices(on, accounts):
    notices = []
    for account in accounts:
        account_notice = notice(account)
        if account_notice["send_on"] == on:
            notices.append(account_notice)
    return {
        "on": on,
        "notices": notices,
        "total_due_cents": sum(item["amount_due_cents"] for item in notices),
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return notice(request["account"])
    if request.get("command") == "export":
        return export_notices(request["accounts"])
    if request.get("command") == "batch":
        return batch_notices(request["on"], request["accounts"])
    if request.get("command") == "support_replay":
        return {"case_id": "IOS-1842", "notice": ios_1842_notice(request["account"])}
    if request.get("command") == "compat_notice":
        return {"release": "1.0", "notice": release_1_0_notice(request["account"])}
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
