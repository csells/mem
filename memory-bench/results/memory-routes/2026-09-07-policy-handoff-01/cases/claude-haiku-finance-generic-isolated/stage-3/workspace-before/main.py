#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request.get("line")
        release = request.get("release", "1.0")

        uncapped_credit = line["charge_cents"] // 10
        credit_cents = min(uncapped_credit, 2400)
        amount_due_cents = line["charge_cents"] - credit_cents

        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "1.0")

        total_charge_cents = sum(line["charge_cents"] for line in lines)
        uncapped_credit = total_charge_cents // 10
        credit_cents = min(uncapped_credit, 2400)
        amount_due_cents = total_charge_cents - credit_cents

        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
