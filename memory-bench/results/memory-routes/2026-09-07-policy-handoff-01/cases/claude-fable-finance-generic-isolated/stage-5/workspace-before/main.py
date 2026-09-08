#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

PRODUCT = "Meridian Credits"

# Each release is a Finance-approved credit agreement. An omitted release
# selects the current agreement; explicit supported releases stay supported
# once introduced. Fields:
#   rate_percent  - uncapped credit as a percentage of charge_cents, floored
#                   separately per line to integer cents
#   cap_cents     - credit cap shared by every line in the same cap group
#   cap_group     - key deriving a line's cap group; distinct groups have
#                   independent caps
#   priority      - order in which lines within a cap group are served
RELEASES = {
    # Release 1.0: 10%, 2400-cent cap per account_id (across subscriptions),
    # earliest service_on first, ties by increasing line_id.
    "1.0": {
        "rate_percent": 10,
        "cap_cents": 2400,
        "cap_group": lambda line: line["account_id"],
        "priority": lambda line: (line["service_on"], line["line_id"]),
    },
    # Release 2.0: 15%, 3000-cent cap per (account_id, subscription_id),
    # largest charge_cents first, ties by increasing line_id.
    "2.0": {
        "rate_percent": 15,
        "cap_cents": 3000,
        "cap_group": lambda line: (line["account_id"], line["subscription_id"]),
        "priority": lambda line: (-line["charge_cents"], line["line_id"]),
    },
}
CURRENT_RELEASE = "2.0"


def uncapped_credit(line, rules):
    """The release's rate applied to charge_cents, rounded down per line."""
    return line["charge_cents"] * rules["rate_percent"] // 100


def assign_credits(lines, rules):
    """Assign capped credit per line for one complete monthly statement.

    Lines are served in the release's priority order. Each line receives its
    uncapped credit up to its cap group's remaining cap; later lines in the
    group receive only the remainder, or zero.

    Returns {line_id: credit_cents}.
    """
    credits = {}
    remaining = {}
    for line in sorted(lines, key=rules["priority"]):
        group = rules["cap_group"](line)
        left = remaining.get(group, rules["cap_cents"])
        credit = min(uncapped_credit(line, rules), left)
        remaining[group] = left - credit
        credits[line["line_id"]] = credit
    return credits


def resolve_release(request):
    release = request.get("release", CURRENT_RELEASE)
    if release not in RELEASES:
        return None
    return release


def quote(request):
    """Quote one charge line, treated as the entire statement."""
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    line = request["line"]
    credit = assign_credits([line], RELEASES[release])[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total(request):
    """Total one complete monthly statement's charge set.

    Caps are applied across the whole set (per the release's cap scope), so
    this is not the sum of independent single-line quotes.
    """
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    lines = request["lines"]
    credit = sum(assign_credits(lines, RELEASES[release]).values())
    charges = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": charges - credit,
    }


def statement(request):
    """Itemize one complete monthly statement's charge set.

    Same cap groups and priority as total; the per-line credits are shown in
    the input line order, and the overall amounts equal total's for the same
    input.
    """
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    lines = request["lines"]
    credits = assign_credits(lines, RELEASES[release])
    items = [
        {
            "line_id": line["line_id"],
            "credit_cents": credits[line["line_id"]],
            "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
        }
        for line in lines
    ]
    return {
        "release": release,
        "lines": items,
        "credit_cents": sum(item["credit_cents"] for item in items),
        "amount_due_cents": sum(item["amount_due_cents"] for item in items),
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": PRODUCT}
    if command == "quote":
        return quote(request)
    if command == "total":
        return total(request)
    if command == "statement":
        return statement(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
