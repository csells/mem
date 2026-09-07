#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta

NOTICE_LEAD_DAYS = 21
LOYALTY_MIN_YEARS = 2
LOYALTY_RATE_PERCENT = 10
LOYALTY_MAX_CENTS = 2400


def loyalty_credit_cents(account):
    if not account["autopay"] or account["completed_years"] < LOYALTY_MIN_YEARS:
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
