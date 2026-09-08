#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    
    if request.get("command") == "quote":
        return handle_quote(request)
    
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
    
    # For release 1.0: credit is 10% of charge_cents, rounded down
    uncapped_credit = line["charge_cents"] // 10
    
    # Apply 2400-cent cap per subscription (account_id, subscription_id) pair
    # Since we're processing a single line, we treat it as the only line in that group
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


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
