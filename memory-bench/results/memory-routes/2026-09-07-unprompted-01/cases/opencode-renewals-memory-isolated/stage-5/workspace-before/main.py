#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import datetime, timedelta


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    
    if request.get("command") == "notice":
        account = request.get("account", {})
        
        # Extract account details
        customer_id = account.get("customer_id")
        renewal_on = account.get("renewal_on")
        plan_cents = account.get("plan_cents")
        completed_years = account.get("completed_years")
        autopay = account.get("autopay")
        
        # Validate required fields
        if not all([customer_id, renewal_on, plan_cents is not None, completed_years is not None, autopay is not None]):
            return {"error": "missing_fields"}
        
        # Parse renewal date
        try:
            renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "invalid_date"}
        
        # Calculate send_on date (14 days before renewal)
        send_on_date = renewal_date - timedelta(days=14)
        send_on = send_on_date.strftime("%Y-%m-%d")
        
        # Calculate loyalty credit
        credit_cents = 0
        if completed_years >= 3:
            credit_cents = min(plan_cents // 10 * 15 // 100, 3600)
        
        # Calculate amount due
        amount_due_cents = plan_cents - credit_cents
        
        return {
            "customer_id": customer_id,
            "send_on": send_on,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    
    if request.get("command") == "support_replay":
        # Validate required fields
        case_id = request.get("case_id")
        account = request.get("account", {})
        
        if not case_id:
            return {"error": "missing_fields"}
        
        # Extract account details
        customer_id = account.get("customer_id")
        renewal_on = account.get("renewal_on")
        plan_cents = account.get("plan_cents")
        completed_years = account.get("completed_years")
        autopay = account.get("autopay")
        
        # Validate required fields
        if not all([customer_id, renewal_on, plan_cents is not None, completed_years is not None, autopay is not None]):
            return {"error": "missing_fields"}
        
        # Parse renewal date
        try:
            renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "invalid_date"}
        
        # Calculate send_on date (14 days before renewal)
        send_on_date = renewal_date - timedelta(days=14)
        send_on = send_on_date.strftime("%Y-%m-%d")
        
        # Calculate loyalty credit
        credit_cents = 0
        if completed_years >= 3:
            credit_cents = min(plan_cents // 10 * 15 // 100, 3600)
        
        # Calculate amount due
        amount_due_cents = plan_cents - credit_cents
        
        return {
            "case_id": case_id,
            "notice": {
                "customer_id": customer_id,
                "send_on": send_on,
                "credit_cents": credit_cents,
                "amount_due_cents": amount_due_cents
            }
        }
    
    if request.get("command") == "export":
        accounts = request.get("accounts", [])
        
        # Build CSV content
        csv_lines = ["customer_id,send_on,credit_cents,amount_due_cents"]
        
        for account in accounts:
            # Extract account details
            customer_id = account.get("customer_id")
            renewal_on = account.get("renewal_on")
            plan_cents = account.get("plan_cents")
            completed_years = account.get("completed_years")
            autopay = account.get("autopay")
            
            # Validate required fields
            if not all([customer_id, renewal_on, plan_cents is not None, completed_years is not None, autopay is not None]):
                return {"error": "missing_fields"}
            
            # Parse renewal date
            try:
                renewal_date = datetime.strptime(renewal_on, "%Y-%m-%d").date()
            except ValueError:
                return {"error": "invalid_date"}
            
            # Calculate send_on date (14 days before renewal)
            send_on_date = renewal_date - timedelta(days=14)
            send_on = send_on_date.strftime("%Y-%m-%d")
            
        # Calculate loyalty credit
        credit_cents = 0
        if completed_years >= 3:
            credit_cents = min(plan_cents * 15 // 100, 3600)
            
            # Calculate amount due
            amount_due_cents = plan_cents - credit_cents
            
            # Format CSV row with proper quoting
            row = []
            for value in [customer_id, send_on, str(credit_cents), str(amount_due_cents)]:
                # Check if we need to quote the field
                if any(char in value for char in [',', '"', '\r', '\n']):
                    # Escape double quotes and wrap in quotes
                    escaped_value = value.replace('"', '""')
                    row.append(f'"{escaped_value}"')
                else:
                    row.append(value)
            
            csv_lines.append(','.join(row))
        
        csv_content = '\n'.join(csv_lines) + '\n'
        return {
            "csv": csv_content,
            "count": len(accounts)
        }
    
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
