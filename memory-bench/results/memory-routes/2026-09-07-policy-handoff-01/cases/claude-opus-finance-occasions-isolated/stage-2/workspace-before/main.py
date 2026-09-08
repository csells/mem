#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"
CREDIT_RATE_PERCENT = 10
GROUP_CAP_CENTS = 2400


def uncapped_credit(line):
    """Credit a line earns before its cap group is applied, rounded down."""
    return line["charge_cents"] * CREDIT_RATE_PERCENT // 100


def assign_credits(lines):
    """Map line_id to assigned credit for a whole statement's charge lines.

    The 2400-cent cap is shared by all lines of one (account_id,
    subscription_id) subscription. Within a group, credit goes to the earliest
    service_on first, then to the lower line_id, until the cap is used up.
    """
    remaining = {}
    assigned = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        left = remaining.get(group, GROUP_CAP_CENTS)
        credit = min(uncapped_credit(line), left)
        remaining[group] = left - credit
        assigned[line["line_id"]] = credit
    return assigned


def quote_line(line):
    """Quote one charge line treated as the entire statement."""
    credit = assign_credits([line])[line["line_id"]]
    return {
        "release": CURRENT_RELEASE,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
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
