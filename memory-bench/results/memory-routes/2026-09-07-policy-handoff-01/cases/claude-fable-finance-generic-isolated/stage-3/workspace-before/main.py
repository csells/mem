#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

PRODUCT = "Meridian Credits"

# Release "1.0" is the initial Finance-approved credit agreement. An omitted
# release selects the current agreement; explicit supported releases stay
# supported once introduced.
CURRENT_RELEASE = "1.0"
SUPPORTED_RELEASES = ("1.0",)

CREDIT_RATE_PERCENT = 10
ACCOUNT_CAP_CENTS = 2400


def uncapped_credit(line):
    """10% of charge_cents, rounded down separately per line."""
    return line["charge_cents"] * CREDIT_RATE_PERCENT // 100


def assign_credits(lines):
    """Assign capped credit per line for one complete monthly statement.

    Release 1.0: the 2400-cent cap is shared by every line with the same
    account_id (across its subscriptions); distinct accounts have independent
    caps. Within a cap group, lines are served earliest service_on first, ties
    by increasing line_id (code-point order). Each line receives its uncapped
    credit up to the group's remaining cap.

    Returns {line_id: credit_cents}.
    """
    credits = {}
    remaining = {}
    ordered = sorted(lines, key=lambda l: (l["service_on"], l["line_id"]))
    for line in ordered:
        group = line["account_id"]
        left = remaining.get(group, ACCOUNT_CAP_CENTS)
        credit = min(uncapped_credit(line), left)
        remaining[group] = left - credit
        credits[line["line_id"]] = credit
    return credits


def resolve_release(request):
    release = request.get("release", CURRENT_RELEASE)
    if release not in SUPPORTED_RELEASES:
        return None
    return release


def quote(request):
    """Quote one charge line, treated as the entire statement."""
    release = resolve_release(request)
    if release is None:
        return {"error": "unsupported_release"}
    line = request["line"]
    credit = assign_credits([line])[line["line_id"]]
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
    credit = sum(assign_credits(lines).values())
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
