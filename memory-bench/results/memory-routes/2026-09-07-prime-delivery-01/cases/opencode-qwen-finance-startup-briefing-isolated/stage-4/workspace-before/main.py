#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        charge_cents = line["charge_cents"]
        release = request.get("release", "2.0")
        
        if release == "1.0":
            # Original calculation: 10% rounded down, capped at 2400
            uncapped_credit = charge_cents // 10
            credit_cents = min(uncapped_credit, 2400)
        else:
            # Release 2.0 calculation: 15% rounded down, capped at 3000 per account group
            uncapped_credit = charge_cents * 15 // 100
            credit_cents = min(uncapped_credit, 3000)
        
        # Calculate amount due
        amount_due_cents = charge_cents - credit_cents
        
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
            "line_id": line["line_id"]
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")
        
        if release == "1.0":
            # Original calculation
            total_charge_cents = sum(line["charge_cents"] for line in lines)
            total_credit_cents = 0
            
            # For each account group, apply 2400 cap to the total credit
            account_groups = {}
            for line in lines:
                account_id = line["account_id"]
                if account_id not in account_groups:
                    account_groups[account_id] = 0
            
            for line in lines:
                charge_cents = line["charge_cents"]
                uncapped_credit = charge_cents // 10
                credit_cents = min(uncapped_credit, 2400)
                account_id = line["account_id"]
                account_groups[account_id] += credit_cents
            
            # Apply caps to each group
            for account_id in account_groups:
                account_groups[account_id] = min(account_groups[account_id], 2400)
            
            total_credit_cents = sum(account_groups.values())
        else:
            # Release 2.0 calculation
            total_charge_cents = sum(line["charge_cents"] for line in lines)
            total_credit_cents = 0
            
            # Group lines by account_id and process each group
            account_groups = {}
            for line in lines:
                account_id = line["account_id"]
                if account_id not in account_groups:
                    account_groups[account_id] = []
                account_groups[account_id].append(line)
            
            # Process each group individually applying the 3000 cap
            for account_id, group_lines in account_groups.items():
                # Sort lines by charge_cents descending, then by line_id ascending
                group_lines.sort(key=lambda x: (-x["charge_cents"], x["line_id"]))
                
                # Calculate credit for each line in order, applying the cap
                group_cap = 3000
                group_credit = 0
                
                for line in group_lines:
                    charge_cents = line["charge_cents"]
                    uncapped_credit = charge_cents * 15 // 100
                    
                    # Assign credit up to the remaining cap
                    available_credit = min(uncapped_credit, group_cap - group_credit)
                    line_credit = available_credit
                    group_credit += line_credit
                    
                    # Update line with actual credit (though we don't return this in final response)
                    line["credit_cents"] = line_credit
                
                total_credit_cents += group_credit 
            
        total_amount_due_cents = total_charge_cents - total_credit_cents
        
        return {
            "release": release,
            "credit_cents": total_credit_cents,
            "amount_due_cents": total_amount_due_cents
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
