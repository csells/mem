#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def get_credit_percent(release):
    """Return credit percentage for a release."""
    return 10 if release == "1.0" else 15


def get_cap_cents(release):
    """Return credit cap for a release."""
    return 2400 if release == "1.0" else 3000


def quote_single_line(line, release):
    """Quote a single charge line."""
    charge_cents = line["charge_cents"]
    credit_percent = get_credit_percent(release)
    uncapped_credit = charge_cents * credit_percent // 100
    cap_cents = get_cap_cents(release)
    assigned_credit = min(uncapped_credit, cap_cents)
    amount_due = charge_cents - assigned_credit
    return {
        "release": release,
        "credit_cents": assigned_credit,
        "amount_due_cents": amount_due,
        "line_id": line["line_id"],
    }


def handle_total(request):
    release = request.get("release", "2.0")
    lines = request.get("lines", [])

    subscriptions = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        if key not in subscriptions:
            subscriptions[key] = []
        subscriptions[key].append(line)

    total_credit = 0
    total_amount_due = 0

    credit_percent = get_credit_percent(release)
    cap_cents = get_cap_cents(release)

    for sub_lines in subscriptions.values():
        if release == "1.0":
            uncapped_credit = sum(line["charge_cents"] * credit_percent // 100 for line in sub_lines)
            assigned_credit = min(uncapped_credit, cap_cents)
            total_credit += assigned_credit
        else:
            sorted_lines = sorted(sub_lines, key=lambda x: (-x["charge_cents"], x["line_id"]))
            remaining_cap = cap_cents
            for line in sorted_lines:
                uncapped = line["charge_cents"] * credit_percent // 100
                assigned = min(uncapped, remaining_cap)
                total_credit += assigned
                remaining_cap -= assigned

        total_charge_cents = sum(line["charge_cents"] for line in sub_lines)
        total_amount_due += total_charge_cents

    total_amount_due -= total_credit

    return {
        "release": release,
        "credit_cents": total_credit,
        "amount_due_cents": total_amount_due,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", "2.0")
        return quote_single_line(request["line"], release)
    if request.get("command") == "total":
        return handle_total(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
