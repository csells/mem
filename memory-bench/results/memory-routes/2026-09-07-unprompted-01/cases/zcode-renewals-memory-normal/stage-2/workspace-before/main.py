#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import date, timedelta


def notice(account):
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
