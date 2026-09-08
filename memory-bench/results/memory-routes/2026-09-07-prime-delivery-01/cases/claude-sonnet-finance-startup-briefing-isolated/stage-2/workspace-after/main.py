#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CREDIT_CAP_CENTS = 2400


def credit_for_charge(charge_cents):
    return min(charge_cents * 10 // 100, CREDIT_CAP_CENTS)


def quote_line(line):
    charge_cents = line["charge_cents"]
    credit_cents = credit_for_charge(charge_cents)
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def quote_total(lines):
    subscription_charges = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        subscription_charges[key] = subscription_charges.get(key, 0) + line["charge_cents"]
    total_charge_cents = sum(subscription_charges.values())
    credit_cents = sum(credit_for_charge(c) for c in subscription_charges.values())
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": total_charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"])
    if command == "total":
        return quote_total(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
