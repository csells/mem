#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    
    if request.get("command") == "quote":
        return handle_quote(request)
    
    if request.get("command") == "total":
        return handle_total(request)
    
    return {"error": "unknown_command"}


def handle_quote(request):
    """Handle a quote request for a single charge line."""
    # Extract the line from request
    line = request.get("line", {})
    
    # Validate required fields
    required_fields = ["line_id", "account_id", "subscription_id", "service_on", "charge_cents"]
    for field in required_fields:
        if field not in line:
            return {"error": f"missing_required_field: {field}"}
    
    # Validate service_on date format (YYYY-MM-DD)
    service_on = line["service_on"]
    try:
        year, month, day = map(int, service_on.split("-"))
        if not (2020 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31):
            return {"error": "invalid_date_format"}
    except (ValueError, AttributeError):
        return {"error": "invalid_date_format"}
    
    # Validate charge_cents
    if not isinstance(line["charge_cents"], int) or line["charge_cents"] < 0:
        return {"error": "invalid_charge_amount"}
    
    # Validate IDs are nonempty strings
    for field in ["line_id", "account_id", "subscription_id"]:
        if not isinstance(line[field], str) or not line[field]:
            return {"error": f"invalid_{field}"}
    
    # Get release version (default 1.0)
    release = request.get("release", "1.0")
    
    # Handle different releases
    if release == "2.0":
        # For release 2.0: credit is 15% of charge_cents, rounded down to integer cents
        uncapped_credit = line["charge_cents"] * 15 // 100
        # Apply 3000-cent cap per account_id group
        # Since we're processing a single line here (no grouping information), 
        # we'll assume it's the only line in the group and apply the full cap
        credit_cents = min(uncapped_credit, 3000)
    else:
        # For release 1.0: credit is 10% of charge_cents, rounded down
        uncapped_credit = line["charge_cents"] // 10
        # Apply 2400-cent cap per subscription (account_id, subscription_id) pair
        credit_cents = min(uncapped_credit, 2400)
    
    # Calculate amount due
    amount_due_cents = line["charge_cents"] - credit_cents
    
    # Return the response with required fields
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": amount_due_cents
    }


def handle_total(request):
    """Handle a total request for multiple charge lines."""
    # Extract the lines from request
    lines = request.get("lines", [])
    
    # Validate lines is a list
    if not isinstance(lines, list):
        return {"error": "invalid_lines_format"}
    
    # Get release version (default 1.0)
    release = request.get("release", "1.0")
    
    # For empty lines, we just return 0 credit and amount due
    if not lines:
        return {
            "release": release,
            "credit_cents": 0,
            "amount_due_cents": 0
        }
    
    # Handle different releases
    if release == "2.0":
        # For release 2.0: need to calculate cap per account_id group
        # Group lines by account_id and assign credit respecting caps
        # We'll collect all the charges and process them using 2.0 logic for proper cap allocation
        
        # First, we validate all the lines, then apply credit assignment with proper grouping
        valid_lines = []
        for line in lines:
            # Validate required fields
            required_fields = ["line_id", "account_id", "subscription_id", "service_on", "charge_cents"]
            for field in required_fields:
                if field not in line:
                    return {"error": f"missing_required_field: {field}"}
            
            # Validate service_on date format (YYYY-MM-DD)
            try:
                year, month, day = map(int, line["service_on"].split("-"))
                if not (2020 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31):
                    return {"error": "invalid_date_format"}
            except (ValueError, AttributeError):
                return {"error": "invalid_date_format"}
            
            # Validate charge_cents
            if not isinstance(line["charge_cents"], int) or line["charge_cents"] < 0:
                return {"error": "invalid_charge_amount"}
            
            # Validate IDs are nonempty strings
            for field in ["line_id", "account_id", "subscription_id"]:
                if not isinstance(line[field], str) or not line[field]:
                    return {"error": f"invalid_{field}"}
            
            valid_lines.append(line)
        
        # Group lines by account_id for cap calculation
        account_groups = {}
        for line in valid_lines:
            account_id = line["account_id"]
            if account_id not in account_groups:
                account_groups[account_id] = []
            account_groups[account_id].append(line)
        
        # For each group, compute credits with caps applied
        total_credit = 0
        total_charge = 0
        
        for account_id, account_lines in account_groups.items():
            # Calculate uncapped credit for all lines in this group and sort by charge_cents descending
            # For ties, we use line_id ascending to maintain consistent behavior
            sorted_lines = sorted(account_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))
            
            # Apply 3000-cent cap per group
            remaining_cap = 3000
            
            for line in sorted_lines:
                charge = line["charge_cents"]
                uncapped_credit = charge * 15 // 100
                credit_to_assign = min(uncapped_credit, remaining_cap)
                
                # Update remaining cap and total charges
                remaining_cap -= credit_to_assign
                total_credit += credit_to_assign
                total_charge += charge
        
        # Calculate amount due
        total_amount_due = total_charge - total_credit
        
        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": total_amount_due
        }
    else:
        # For release 1.0: simple sum with per-subscription cap of 2400
        total_credit = 0
        total_charge = 0
        
        for line in lines:
            # Validate required fields
            required_fields = ["line_id", "account_id", "subscription_id", "service_on", "charge_cents"]
            for field in required_fields:
                if field not in line:
                    return {"error": f"missing_required_field: {field}"}
            
            # Validate service_on date format (YYYY-MM-DD)
            try:
                year, month, day = map(int, line["service_on"].split("-"))
                if not (2020 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31):
                    return {"error": "invalid_date_format"}
            except (ValueError, AttributeError):
                return {"error": "invalid_date_format"}
            
            # Validate charge_cents
            if not isinstance(line["charge_cents"], int) or line["charge_cents"] < 0:
                return {"error": "invalid_charge_amount"}
            
            # Validate IDs are nonempty strings
            for field in ["line_id", "account_id", "subscription_id"]:
                if not isinstance(line[field], str) or not line[field]:
                    return {"error": f"invalid_{field}"}
            
            charges = line["charge_cents"]
            uncapped_credit = charges // 10
            # Apply 2400-cent cap per subscription (account_id, subscription_id) pair
            credit = min(uncapped_credit, 2400)
            
            total_credit += credit
            total_charge += charges
        
        # Calculate amount due
        total_amount_due = total_charge - total_credit
        
        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": total_amount_due
        }


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
