#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "total":
        lines = request.get("lines", [])
        credit_cents = 0
        amount_due_cents = 0
        for line in lines:
            # Calculate credit as 10% of charge_cents, capped at 20000
            line_credit = min(line["charge_cents"] // 10, 20000)
            credit_cents += line_credit
            # Calculate amount due after applying credit
            amount_due_cents += max(0, line["charge_cents"] - line_credit)
        return {
            "release": request.get("release", "1.0"),
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    if request.get("command") == "quote":
        # For quote command, we'll use the existing logic from the example
        line = request.get("line")
        line_credit = min(line["charge_cents"] // 10, 20000)
        amount_due_cents = max(0, line["charge_cents"] - line_credit)
        return {
            "release": request.get("release", "1.0"),
            "credit_cents": line_credit,
            "amount_due_cents": amount_due_cents,
            "line_id": line["line_id"]
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
