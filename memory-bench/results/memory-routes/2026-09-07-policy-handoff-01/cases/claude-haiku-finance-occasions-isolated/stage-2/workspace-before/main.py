#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request.get("line")
        charge_cents = line.get("charge_cents")
        uncapped_credit = charge_cents // 10
        credit_cents = min(uncapped_credit, 2400)
        amount_due_cents = charge_cents - credit_cents
        return {
            "release": "1.0",
            "line_id": line.get("line_id"),
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
