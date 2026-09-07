#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys
from datetime import datetime, timedelta


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    elif request.get("command") == "support_replay":
        # Handle the support_replay command for IOS-1842 case
        case_id = request.get("case_id")
        if case_id != "IOS-1842":
            return {"error": "unsupported_case"}
        
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
        
        # Calculate send_on date (14 calendar days before renewal)
        send_date = renewal_date - timedelta(days=14)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit and amount due according to new policy
        credit_cents = 0
        amount_due_cents = account["plan_cents"]
        
        # Apply loyalty credit if completed at least 3 years (autopay doesn't affect eligibility)
        if account.get("completed_years", 0) >= 3:
            credit_cents = min(account["plan_cents"] * 15 // 100, 3600)
            amount_due_cents = account["plan_cents"] - credit_cents
        
        return {
            "case_id": case_id,
            "notice": {
                "customer_id": account["customer_id"],
                "send_on": send_on,
                "credit_cents": credit_cents,
                "amount_due_cents": amount_due_cents
            }
        }
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
        
        # Calculate send_on date (14 calendar days before renewal)
        send_date = renewal_date - timedelta(days=14)
        send_on = send_date.strftime("%Y-%m-%d")
        
        # Calculate credit and amount due according to new policy
        credit_cents = 0
        amount_due_cents = account["plan_cents"]
        
        # Apply loyalty credit if completed at least 3 years (autopay doesn't affect eligibility)
        if account.get("completed_years", 0) >= 3:
            credit_cents = min(account["plan_cents"] * 15 // 100, 3600)
            amount_due_cents = account["plan_cents"] - credit_cents
        
        return {
            "customer_id": account["customer_id"],
            "send_on": send_on,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    elif request.get("command") == "export":
        accounts = request.get("accounts", [])
        
        # Build CSV content
        csv_lines = ["customer_id,send_on,credit_cents,amount_due_cents"]
        
        for account in accounts:
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
            
            # Format fields for CSV
            customer_id = account["customer_id"]
            # Quote fields that contain special characters 
            if ',' in customer_id or '"' in customer_id or '\r' in customer_id or '\n' in customer_id:
                customer_id = f'"{customer_id.replace("\"", "\"\"")}"'
            
            # Format the CSV row
            csv_line = f"{customer_id},{send_on},{credit_cents},{amount_due_cents}"
            csv_lines.append(csv_line)
        
        # Join with newlines and ensure final newline
        csv_content = "\n".join(csv_lines) + "\n"
        
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
