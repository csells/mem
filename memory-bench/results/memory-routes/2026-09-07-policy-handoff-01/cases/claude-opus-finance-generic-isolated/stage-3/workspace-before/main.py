#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"
CREDIT_RATE_DIVISOR = 10  # 10% of the charge
GROUP_CAP_CENTS = 2400


def assign_credits(lines):
    """Map line_id to the credit assigned by the release 1.0 agreement.

    Each line earns 10% of its charge, rounded down. Lines sharing an
    (account_id, subscription_id) pair share one cap, consumed earliest
    service date first and, for equal dates, by increasing line_id.
    """
    remaining = {}
    credits = {}
    order = sorted(lines, key=lambda line: (line["service_on"], line["line_id"]))
    for line in order:
        group = (line["account_id"], line["subscription_id"])
        available = remaining.get(group, GROUP_CAP_CENTS)
        credit = min(line["charge_cents"] // CREDIT_RATE_DIVISOR, available)
        remaining[group] = available - credit
        credits[line["line_id"]] = credit
    return credits


def quote(request):
    """Quote one charge line treated as an entire monthly statement."""
    line = request["line"]
    credit = assign_credits([line])[line["line_id"]]
    return {
        "release": CURRENT_RELEASE,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total(request):
    """Quote a whole monthly statement, sharing caps across its charge lines."""
    lines = request["lines"]
    credit = sum(assign_credits(lines).values())
    charges = sum(line["charge_cents"] for line in lines)
    return {
        "release": CURRENT_RELEASE,
        "credit_cents": credit,
        "amount_due_cents": charges - credit,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote(request)
    if command == "total":
        return total(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
