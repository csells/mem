#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
from datetime import date, timedelta
import json
import sys

LOYALTY_MIN_YEARS = 2
LOYALTY_CAP_CENTS = 2400
NOTICE_LEAD_DAYS = 21


def notice(account):
    plan_cents = account["plan_cents"]
    if account["autopay"] and account["completed_years"] >= LOYALTY_MIN_YEARS:
        credit_cents = min(plan_cents * 10 // 100, LOYALTY_CAP_CENTS)
    else:
        credit_cents = 0
    send_on = date.fromisoformat(account["renewal_on"]) - timedelta(days=NOTICE_LEAD_DAYS)
    return {
        "customer_id": account["customer_id"],
        "send_on": send_on.isoformat(),
        "credit_cents": credit_cents,
        "amount_due_cents": plan_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return notice(request["account"])
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
