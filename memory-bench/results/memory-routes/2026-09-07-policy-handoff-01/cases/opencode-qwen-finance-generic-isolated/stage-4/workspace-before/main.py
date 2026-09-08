#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")
        
        total_charge = 0
        total_credit = 0
        
        # Group lines by account_id for cap calculation
        account_groups = {}
        for line in lines:
            account_id = line.get("account_id", "")
            if account_id not in account_groups:
                account_groups[account_id] = []
            account_groups[account_id].append(line)
        
        # Process each account group
        for account_id, account_lines in account_groups.items():
            # Sort lines by charge_cents (descending) then by line_id (ascending) 
            account_lines.sort(key=lambda x: (-x.get("charge_cents", 0), x.get("line_id", "")))
            
            # For release 2.0: credit is 15% of charge, rounded down
            if release == "2.0":
                cap_remaining = 3000  # 3000 cents cap per account group
                
                for line in account_lines:
                    charge = line.get("charge_cents", 0)
                    uncapped_credit = int(charge * 0.15)  # 15% rounded down
                    credit_to_assign = min(uncapped_credit, cap_remaining)
                    cap_remaining -= credit_to_assign
                    total_credit += credit_to_assign
                    
                    # Store credit for this line (for later use if needed)
                    line["calculated_credit"] = credit_to_assign
            else:
                # For release 1.0: credit is 10% of charge, truncated
                for line in account_lines:
                    charge = line.get("charge_cents", 0)
                    credit = int(charge * 0.1)
                    total_credit += credit
            
            # Sum up charges for this group 
            group_charge = sum(line.get("charge_cents", 0) for line in account_lines)
            total_charge += group_charge
        
        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": total_charge - total_credit
        }
    
    if request.get("command") == "quote":
        line = request.get("line", {})
        release = request.get("release", "2.0")
        
        charge = line.get("charge_cents", 0)
        
        # For release 2.0: credit is 15% of charge, rounded down
        if release == "2.0":
            credit = int(charge * 0.15)  # This truncates toward zero
            amount_due = charge - credit
        else:
            # For release 1.0: credit is 10% of charge, truncated (floor operation)
            credit = int(charge * 0.1)  # This truncates toward zero
            amount_due = charge - credit
        
        return {
            "release": release,
            "credit_cents": credit,
            "amount_due_cents": amount_due,
            "line_id": line.get("line_id", "")
        }
        
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
