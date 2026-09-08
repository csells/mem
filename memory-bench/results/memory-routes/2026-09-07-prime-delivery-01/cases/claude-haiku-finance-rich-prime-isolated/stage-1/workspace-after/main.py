#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def quote_single_line(line, release):
    """Quote a single charge line."""
    charge_cents = line["charge_cents"]
    uncapped_credit = charge_cents // 10
    cap_cents = 2400
    assigned_credit = min(uncapped_credit, cap_cents)
    amount_due = charge_cents - assigned_credit
    return {
        "release": release,
        "credit_cents": assigned_credit,
        "amount_due_cents": amount_due,
        "line_id": line["line_id"],
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", "1.0")
        return quote_single_line(request["line"], release)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
