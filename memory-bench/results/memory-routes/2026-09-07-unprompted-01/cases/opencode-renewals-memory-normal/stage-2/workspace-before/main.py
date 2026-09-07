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
        # Validate account fields
        required_fields = ["customer_id", "renewal_on", "plan_cents", "completed_years", "autopay"]
        for field in required_fields:
            if field not in account:
                return {"error": f"missing_required_field: {field}"}
        
        # Parse renewal date
        try:
            renewal_date = datetime.strptime(account["renewal_on"], "%Y-%m-%d").date()
        except ValueError:
            return {"error": "invalid_renewal_date"}
        
        # Calculate send_on date (21 calendar days before renewal)
        send_date = renewal_date - timedelta(days=21)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit and amount due
        credit_cents = 0
        amount_due_cents = account["plan_cents"]
        
        # Apply loyalty credit only if autopay is enabled AND completed at least 2 years
        if account.get("autopay", False) and account.get("completed_years", 0) >= 2:
            credit_cents = min(account["plan_cents"] // 10, 2400)
            amount_due_cents = account["plan_cents"] - credit_cents
        
        return {
            "customer_id": account["customer_id"],
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
