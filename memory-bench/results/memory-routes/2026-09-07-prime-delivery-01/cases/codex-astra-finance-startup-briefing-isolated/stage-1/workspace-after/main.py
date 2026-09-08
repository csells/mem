#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        charge = line["charge_cents"]
        credit = min(charge // 10, 2400)
        return {
            "release": "1.0",
            "line_id": line["line_id"],
            "credit_cents": credit,
            "amount_due_cents": charge - credit,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
