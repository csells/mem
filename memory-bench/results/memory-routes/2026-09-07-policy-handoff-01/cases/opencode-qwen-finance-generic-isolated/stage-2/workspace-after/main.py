#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "1.0")
        
        total_charge = 0
        total_credit = 0
        
        for line in lines:
            charge = line.get("charge_cents", 0)
            # For release 1.0: credit is 10% of charge, truncated (floor operation)
            credit = int(charge * 0.1)  # This truncates toward zero
            total_charge += charge
            total_credit += credit
        
        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": total_charge - total_credit
        }
    
    if request.get("command") == "quote":
        line = request.get("line", {})
        release = request.get("release", "1.0")
        
        charge = line.get("charge_cents", 0)
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
