#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    elif request.get("command") == "quote":
        line = request.get("line", {})
        charge_cents = line.get("charge_cents", 0)
        credit_cents = charge_cents // 10  # 10% credit
        amount_due_cents = charge_cents - credit_cents
        return {
            "release": request.get("release", "1.0"),
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
            "line_id": line.get("line_id")
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
