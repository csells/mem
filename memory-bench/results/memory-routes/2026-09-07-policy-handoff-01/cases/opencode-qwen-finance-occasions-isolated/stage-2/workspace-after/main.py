#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    elif request.get("command") == "total":
        # Default to release 1.0 if not specified
        release = request.get("release", "1.0")
        
        # For release 1.0, calculate credit and amount due
        lines = request.get("lines", [])
        
        # Calculate total charge cents
        total_charge_cents = sum(line["charge_cents"] for line in lines)
        
        # Apply credit cap (10% of total charge, max 20000 cents)
        credit_cents = min(total_charge_cents // 10, 20000)
        
        # Calculate amount due (total charge minus credit)
        amount_due_cents = total_charge_cents - credit_cents
        
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
