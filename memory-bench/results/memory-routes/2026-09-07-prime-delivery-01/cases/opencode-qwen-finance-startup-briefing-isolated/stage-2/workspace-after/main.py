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
        
        # Calculate uncapped credit (10% rounded down)
        uncapped_credit = charge_cents // 10
        
        # Apply 2400-cent cap per subscription group
        # For a single line, we just use the uncapped credit since there's no competition for the cap
        credit_cents = min(uncapped_credit, 2400)
        
        # Calculate amount due
        amount_due_cents = charge_cents - credit_cents
        
        return {
            "release": "1.0",
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
            "line_id": line["line_id"]
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
