#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_0 = "1.0"
SUBSCRIPTION_CREDIT_CAP_CENTS = 2400


def quote_line(line):
    """Quote one charge line as a complete, one-line statement."""
    uncapped_credit_cents = line["charge_cents"] // 10
    credit_cents = min(uncapped_credit_cents, SUBSCRIPTION_CREDIT_CAP_CENTS)
    return {
        "release": RELEASE_1_0,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote" and request.get("release", RELEASE_1_0) == RELEASE_1_0:
        return quote_line(request["line"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
