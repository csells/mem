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


def handle_total(request):
    release = request.get("release", "1.0")
    lines = request.get("lines", [])

    subscriptions = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        if key not in subscriptions:
            subscriptions[key] = []
        subscriptions[key].append(line)

    total_credit = 0
    total_amount_due = 0

    cap_cents = 2400
    for sub_lines in subscriptions.values():
        uncapped_credit = sum(line["charge_cents"] // 10 for line in sub_lines)
        assigned_credit = min(uncapped_credit, cap_cents)
        total_credit += assigned_credit

        total_charge_cents = sum(line["charge_cents"] for line in sub_lines)
        sub_amount_due = total_charge_cents - assigned_credit
        total_amount_due += sub_amount_due

    return {
        "release": release,
        "credit_cents": total_credit,
        "amount_due_cents": total_amount_due,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", "1.0")
        return quote_single_line(request["line"], release)
    if request.get("command") == "total":
        return handle_total(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
