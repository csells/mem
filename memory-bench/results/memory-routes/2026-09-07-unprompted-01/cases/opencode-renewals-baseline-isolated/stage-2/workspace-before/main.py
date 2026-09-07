#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import datetime, timedelta


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    elif request.get("command") == "notice":
        account = request.get("account", {})
        customer_id = account.get("customer_id")
        renewal_on = account.get("renewal_on")
        plan_cents = account.get("plan_cents", 0)
        completed_years = account.get("completed_years", 0)
        autopay = account.get("autopay", False)
        
        # Calculate send_on date (21 calendar days before renewal)
        renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d")
        send_date = renewal_date - timedelta(days=21)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit
        credit_cents = 0
        if autopay and completed_years >= 2:
            credit_cents = min(plan_cents // 10, 2400)
        
        # Calculate amount due
        amount_due_cents = plan_cents - credit_cents
        
        return {
            "customer_id": customer_id,
            "send_on": send_on,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
