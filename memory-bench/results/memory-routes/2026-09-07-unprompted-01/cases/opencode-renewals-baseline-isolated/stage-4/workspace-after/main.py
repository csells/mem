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
        
        # Calculate send_on date (14 calendar days before renewal)
        renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d")
        send_date = renewal_date - timedelta(days=14)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit (15% of plan_cents, rounded down, capped at 3600)
        credit_cents = 0
        if completed_years >= 3:
            credit_cents = min(plan_cents * 15 // 100, 3600)
        
        # Calculate amount due
        amount_due_cents = plan_cents - credit_cents
        
        return {
            "customer_id": customer_id,
            "send_on": send_on,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    elif request.get("command") == "export":
        accounts = request.get("accounts", [])
        lines = ["customer_id,send_on,credit_cents,amount_due_cents"]
        
        total_count = 0
        
        for account in accounts:
            customer_id = account.get("customer_id")
            renewal_on = account.get("renewal_on")
            plan_cents = account.get("plan_cents", 0)
            completed_years = account.get("completed_years", 0)
            autopay = account.get("autopay", False)
            
            # Calculate send_on date (14 calendar days before renewal)
            renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d")
            send_date = renewal_date - timedelta(days=14)
            send_on = send_date.strftime("%Y-%m-%d")
            
            # Calculate credit (15% of plan_cents, rounded down, capped at 3600)
            credit_cents = 0
            if completed_years >= 3:
                credit_cents = min(plan_cents * 15 // 100, 3600)
            
            # Calculate amount due
            amount_due_cents = plan_cents - credit_cents
            
            line = f"{customer_id},{send_on},{credit_cents},{amount_due_cents}"
            lines.append(line)
            total_count += 1
        
        csv_output = "\n".join(lines) + "\n"
        
        return {
            "csv": csv_output,
            "count": total_count
        }
    elif request.get("command") == "support_replay":
        case_id = request.get("case_id")
        account = request.get("account", {})
        customer_id = account.get("customer_id")
        renewal_on = account.get("renewal_on")
        plan_cents = account.get("plan_cents", 0)
        completed_years = account.get("completed_years", 0)
        autopay = account.get("autopay", False)
        
        # Calculate send_on date (14 calendar days before renewal)
        renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d")
        send_date = renewal_date - timedelta(days=14)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit (15% of plan_cents, rounded down, capped at 3600)
        credit_cents = 0
        if completed_years >= 3:
            credit_cents = min(plan_cents * 15 // 100, 3600)
        
        # Calculate amount due
        amount_due_cents = plan_cents - credit_cents
        
        notice = {
            "customer_id": customer_id,
            "send_on": send_on,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
        
        return {
            "case_id": case_id,
            "notice": notice
        }
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
