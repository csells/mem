#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    
    release = request.get("release", "2.0")
    
    if request.get("command") == "total":
        lines = request.get("lines", [])
        
        # Special handling for release 1.0 - apply to all lines in one batch
        if release == "1.0":
            total_credit_cents = 0
            total_amount_due_cents = 0
            for line in lines:
                # Release 1.0: 10% of charge_cents, capped at 20000
                line_credit = min(line["charge_cents"] // 10, 20000)
                total_credit_cents += line_credit
                total_amount_due_cents += max(0, line["charge_cents"] - line_credit)
            return {
                "release": release,
                "credit_cents": total_credit_cents,
                "amount_due_cents": total_amount_due_cents
            }
        else:
            # Release 2.0 logic: 15% with 3000 cap per account_id
            # Group lines by account_id
            account_groups = {}
            for line in lines:
                account_id = line["account_id"]
                if account_id not in account_groups:
                    account_groups[account_id] = []
                account_groups[account_id].append(line)
            
            total_credit_cents = 0
            total_amount_due_cents = 0
            
            # Process each account group separately
            for account_id, account_lines in account_groups.items():
                # Calculate uncapped credits for all lines in this group (15%)
                for line in account_lines:
                    uncapped_credit = line["charge_cents"] * 3 // 20  # This is 15% rounded down
                    line["uncapped_credit"] = uncapped_credit
                
                # Sort by charge amount descending, then line_id ascending
                account_lines.sort(key=lambda x: (-x["charge_cents"], x["line_id"]))
                
                # Apply caps (3000 per account)
                group_cap = 3000
                remaining_cap = group_cap
                assigned_credits = []
                
                for line in account_lines:
                    credit = min(line["uncapped_credit"], remaining_cap)
                    line["credit"] = credit
                    remaining_cap -= credit
                    assigned_credits.append(credit)
                
                # Calculate totals for this group
                for i, line in enumerate(account_lines):
                    line["credit"] = assigned_credits[i]
                    total_credit_cents += line["credit"]
                    total_amount_due_cents += max(0, line["charge_cents"] - line["credit"])
            
            return {
                "release": release,
                "credit_cents": total_credit_cents,
                "amount_due_cents": total_amount_due_cents
            }
    
    if request.get("command") == "quote":
        # For quote command, we'll use the existing logic from the example for release 2.0
        line = request.get("line")
        if release == "1.0":
            # Original release 1.0 logic (10% cap at 20000)
            line_credit = min(line["charge_cents"] // 10, 20000)
        else:
            # Release 2.0 logic (15% with 3000 cap per account)
            line_credit = line["charge_cents"] * 3 // 20  # 15% rounded down
            
        amount_due_cents = max(0, line["charge_cents"] - line_credit)
        return {
            "release": release,
            "credit_cents": line_credit,
            "amount_due_cents": amount_due_cents,
            "line_id": line["line_id"]
        }
    
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
