#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request.get("line")
        uncapped_credit = line["charge_cents"] // 10
        cap = 2400
        credit_cents = min(uncapped_credit, cap)
        amount_due_cents = line["charge_cents"] - credit_cents
        return {
            "release": "1.0",
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "1.0")

        # Calculate total uncapped credit across all lines
        total_uncapped_credit = sum(line["charge_cents"] // 10 for line in lines)
        cap = 2400
        total_credit_cents = min(total_uncapped_credit, cap)

        # Calculate total charge and amount due
        total_charge_cents = sum(line["charge_cents"] for line in lines)
        total_amount_due_cents = total_charge_cents - total_credit_cents

        return {
            "release": release,
            "credit_cents": total_credit_cents,
            "amount_due_cents": total_amount_due_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
