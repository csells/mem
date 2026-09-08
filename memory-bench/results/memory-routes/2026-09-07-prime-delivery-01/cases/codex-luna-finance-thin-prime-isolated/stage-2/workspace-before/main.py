#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "1.0"
CREDIT_RATE_DIVISOR = 10
CREDIT_CAP_CENTS = 2400


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        credit_cents = min(line["charge_cents"] // CREDIT_RATE_DIVISOR,
                           CREDIT_CAP_CENTS)
        return {
            "release": request.get("release", CURRENT_RELEASE),
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
            "line_id": line["line_id"],
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
