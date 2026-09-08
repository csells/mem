#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CREDIT_CAP_CENTS = 2400


def uncapped_credit(charge_cents):
    return (charge_cents * 10) // 100


def quote_line(line):
    charge_cents = line["charge_cents"]
    credit_cents = min(uncapped_credit(charge_cents), CREDIT_CAP_CENTS)
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def total_lines(lines):
    groups = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(line)

    total_credit_cents = 0
    total_charge_cents = 0
    for group_lines in groups.values():
        remaining_cap = CREDIT_CAP_CENTS
        ordered = sorted(group_lines, key=lambda l: (l["service_on"], l["line_id"]))
        for line in ordered:
            credit = min(uncapped_credit(line["charge_cents"]), remaining_cap)
            remaining_cap -= credit
            total_credit_cents += credit
        total_charge_cents += sum(l["charge_cents"] for l in group_lines)

    return {
        "release": "1.0",
        "credit_cents": total_credit_cents,
        "amount_due_cents": total_charge_cents - total_credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"])
    if command == "total":
        return total_lines(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
