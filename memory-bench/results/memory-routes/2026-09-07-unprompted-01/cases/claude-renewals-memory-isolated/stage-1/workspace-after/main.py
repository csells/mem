#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def handle_notice(account):
    renewal = date.fromisoformat(account["renewal_on"])
    send_on = renewal - timedelta(days=21)

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


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if request.get("command") == "notice":
        return handle_notice(request["account"])
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
