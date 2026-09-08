#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CREDIT_CAP_CENTS = 2400


def quote_line(line):
    charge_cents = line["charge_cents"]
    credit_cents = min((charge_cents * 10) // 100, CREDIT_CAP_CENTS)
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
