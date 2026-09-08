#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

PRODUCT = "Meridian Credits"
CURRENT_RELEASE = "2.0"

# Credit agreements by release. Each entry is Finance-approved:
#   "1.0": issue trial-896 (initial agreement, still selectable explicitly)
#   "2.0": issue trial-fxq (current agreement)
# rate_percent: uncapped credit = floor(charge_cents * rate_percent / 100) per line.
# cap_cents: shared credit cap for every line in one cap group.
# group_key: fields identifying a cap group.
# priority: sort key deciding which lines in a group draw on the cap first.
RELEASES = {
    "1.0": {
        "rate_percent": 10,
        "cap_cents": 2400,
        # All of an account's subscriptions share one cap.
        "group_key": lambda line: line["account_id"],
        # Earliest service_on first; ties by increasing line_id (code-point order).
        "priority": lambda line: (line["service_on"], line["line_id"]),
    },
    "2.0": {
        "rate_percent": 15,
        "cap_cents": 3000,
        # Each (account_id, subscription_id) pair has its own cap.
        "group_key": lambda line: (line["account_id"], line["subscription_id"]),
        # Largest charge_cents first; ties by increasing line_id (code-point order).
        "priority": lambda line: (-line["charge_cents"], line["line_id"]),
    },
}
SUPPORTED_RELEASES = tuple(RELEASES)


def uncapped_credit(charge_cents, release=CURRENT_RELEASE):
    """The release's rate applied to the charge, rounded down per line to integer cents."""
    return charge_cents * RELEASES[release]["rate_percent"] // 100


def assign_credits(lines, release=CURRENT_RELEASE):
    """Assign credits to every line of one complete monthly statement.

    Returns {line_id: credit_cents}. The release's cap is shared by all lines in
    the same cap group; distinct groups have independent caps. Within a group,
    lines draw on the cap in the release's priority order: each line receives its
    uncapped credit up to the group's remaining cap, later lines only the
    remainder or zero.
    """
    agreement = RELEASES[release]
    credits = {}
    remaining_by_group = {}
    for line in sorted(lines, key=agreement["priority"]):
        group = agreement["group_key"](line)
        remaining = remaining_by_group.get(group, agreement["cap_cents"])
        credit = min(uncapped_credit(line["charge_cents"], release), remaining)
        remaining_by_group[group] = remaining - credit
        credits[line["line_id"]] = credit
    return credits


def resolve_release(request):
    release = request.get("release", CURRENT_RELEASE)
    if release not in SUPPORTED_RELEASES:
        return None
    return release


def quote(request):
    """Quote one charge line, treating it as the entire statement."""
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    line = request["line"]
    credit = assign_credits([line], release)[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total(request):
    """Total one complete monthly statement; caps are shared across its lines."""
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    lines = request["lines"]
    credit = sum(assign_credits(lines, release).values())
    charges = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": charges - credit,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": PRODUCT}
    if command == "quote":
        return quote(request)
    if command == "total":
        return total(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
