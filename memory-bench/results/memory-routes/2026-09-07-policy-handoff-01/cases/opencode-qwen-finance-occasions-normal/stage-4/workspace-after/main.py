#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    elif request.get("command") == "quote":
        line = request.get("line", {})
        release = request.get("release", "1.0")
        charge_cents = line.get("charge_cents", 0)
        
        if release == "2.0":
            # Release 2.0: 15% credit rounded down, with 3000-cent cap per account
            uncapped_credit = int(charge_cents * 0.15)  # 15% rounded down
            return {
                "release": release,
                "credit_cents": uncapped_credit,
                "amount_due_cents": charge_cents - uncapped_credit,
                "line_id": line.get("line_id")
            }
        else:
            # Release 1.0: 10% credit rounded down
            credit_cents = charge_cents // 10  # 10% credit
            amount_due_cents = charge_cents - credit_cents
            return {
                "release": release,
                "credit_cents": credit_cents,
                "amount_due_cents": amount_due_cents,
                "line_id": line.get("line_id")
            }
    elif request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "1.0")
        
        if release == "2.0":
            # Release 2.0: Apply 15% credit with caps
            # Group by account_id and calculate credits accordingly
            account_groups = {}
            for line in lines:
                account_id = line.get("account_id")
                if account_id not in account_groups:
                    account_groups[account_id] = []
                account_groups[account_id].append(line)
            
            total_credit_cents = 0
            total_amount_due_cents = 0
            
            # Process each account group
            for account_id, group_lines in account_groups.items():
                # Sort lines by charge_cents (descending), then line_id (ascending) 
                group_lines.sort(key=lambda x: (-x.get("charge_cents", 0), x.get("line_id", "")))
                
                cap_remaining = 3000
                assigned_credits = {}
                
                # Calculate credits for each line in the group
                for line in group_lines:
                    charge_cents = line.get("charge_cents", 0)
                    # Calculate uncapped credit (15% rounded down)
                    uncapped_credit = int(charge_cents * 0.15)
                    
                    # Assign credit up to cap limit
                    assigned_credit = min(uncapped_credit, cap_remaining)
                    cap_remaining -= assigned_credit
                    assigned_credits[line.get("line_id")] = assigned_credit
                    
                    total_credit_cents += assigned_credit
                    total_amount_due_cents += charge_cents - assigned_credit
                
                # Ensure we don't exceed the cap for this group (should not happen with above logic)
                if cap_remaining < 0:
                    raise ValueError("Cap exceeded")
            
            return {
                "release": release,
                "credit_cents": total_credit_cents,
                "amount_due_cents": total_amount_due_cents
            }
        else:
            # Release 1.0: 10% credit rounded down for each line
            total_credit_cents = 0
            total_amount_due_cents = 0
            for line in lines:
                charge_cents = line.get("charge_cents", 0)
                credit_cents = charge_cents // 10  # 10% credit
                amount_due_cents = charge_cents - credit_cents
                total_credit_cents += credit_cents
                total_amount_due_cents += amount_due_cents
            return {
                "release": release,
                "credit_cents": total_credit_cents,
                "amount_due_cents": total_amount_due_cents
            }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
