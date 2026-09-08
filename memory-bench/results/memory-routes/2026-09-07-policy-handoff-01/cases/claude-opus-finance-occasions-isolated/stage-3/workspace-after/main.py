#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "2.0"


def by_service_then_id(line):
    """Release 1.0 priority: earliest service_on, then lower line_id."""
    return (line["service_on"], line["line_id"])


def by_largest_charge_then_id(line):
    """Release 2.0 priority: largest charge_cents, then lower line_id."""
    return (-line["charge_cents"], line["line_id"])


AGREEMENTS = {
    "1.0": {
        "credit_rate_percent": 10,
        "group_cap_cents": 2400,
        "cap_group": lambda line: (line["account_id"], line["subscription_id"]),
        "priority": by_service_then_id,
    },
    "2.0": {
        "credit_rate_percent": 15,
        "group_cap_cents": 3000,
        "cap_group": lambda line: line["account_id"],
        "priority": by_largest_charge_then_id,
    },
}


def uncapped_credit(line, agreement):
    """Credit a line earns before its cap group is applied, rounded down."""
    return line["charge_cents"] * agreement["credit_rate_percent"] // 100


def assign_credits(lines, agreement):
    """Map line_id to assigned credit for a whole statement's charge lines.

    The cap is shared by all lines of one cap group: a (account_id,
    subscription_id) subscription under release 1.0, an account_id under
    release 2.0. Within a group, credit goes to lines in the agreement's
    priority order until the cap is used up.
    """
    remaining = {}
    assigned = {}
    for line in sorted(lines, key=agreement["priority"]):
        group = agreement["cap_group"](line)
        left = remaining.get(group, agreement["group_cap_cents"])
        credit = min(uncapped_credit(line, agreement), left)
        remaining[group] = left - credit
        assigned[line["line_id"]] = credit
    return assigned


def total_statement(lines, release, agreement):
    """Quote a whole monthly statement, sharing each cap group's cap."""
    assigned = assign_credits(lines, agreement)
    credit = sum(assigned.values())
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": sum(line["charge_cents"] for line in lines) - credit,
    }


def quote_line(line, release, agreement):
    """Quote one charge line treated as the entire statement."""
    credit = assign_credits([line], agreement)[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command in ("quote", "total"):
        release = request.get("release", CURRENT_RELEASE)
        agreement = AGREEMENTS[release]
        if command == "quote":
            return quote_line(request["line"], release, agreement)
        return total_statement(request["lines"], release, agreement)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
