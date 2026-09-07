#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta

NOTICE_LEAD_DAYS = 14
LOYALTY_MIN_YEARS = 3
LOYALTY_RATE_PERCENT = 15
LOYALTY_MAX_CENTS = 3600


def loyalty_credit_cents(account):
    if account["completed_years"] < LOYALTY_MIN_YEARS:
        return 0
    return min(account["plan_cents"] * LOYALTY_RATE_PERCENT // 100, LOYALTY_MAX_CENTS)


def notice(account):
    credit = loyalty_credit_cents(account)
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=NOTICE_LEAD_DAYS)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit,
        "amount_due_cents": account["plan_cents"] - credit,
    }


CSV_COLUMNS = ("customer_id", "send_on", "credit_cents", "amount_due_cents")


def csv_field(value):
    text = str(value)
    if any(ch in text for ch in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def export(accounts):
    lines = [",".join(CSV_COLUMNS)]
    for account in accounts:
        row = notice(account)
        lines.append(",".join(csv_field(row[column]) for column in CSV_COLUMNS))
    return {"csv": "".join(line + "\n" for line in lines), "count": len(accounts)}


def replay_notice(account):
    """Notice under the approved release 1.0 rules, pinned for support replay.

    The live notice() policy may change in later releases; these values stay
    fixed for case IOS-1842, so the rules are restated here on purpose.
    """
    if account["autopay"] and account["completed_years"] >= 2:
        credit = min(account["plan_cents"] * 10 // 100, 2400)
    else:
        credit = 0
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=21)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit,
        "amount_due_cents": account["plan_cents"] - credit,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return notice(request["account"])
    if request.get("command") == "export":
        return export(request["accounts"])
    if request.get("command") == "support_replay":
        return {"case_id": request["case_id"], "notice": replay_notice(request["account"])}
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
