#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

PRODUCT = "Meridian Credits"
CURRENT_RELEASE = "1.0"
SUPPORTED_RELEASES = ("1.0",)

# Release 1.0 credit agreement (Finance-approved, see issue trial-896).
CREDIT_RATE_PERCENT = 10
ACCOUNT_CAP_CENTS = 2400


def uncapped_credit(charge_cents):
    """10% of the charge, rounded down separately per line to integer cents."""
    return charge_cents * CREDIT_RATE_PERCENT // 100


def assign_credits(lines):
    """Assign release 1.0 credits to every line of one complete monthly statement.

    Returns {line_id: credit_cents}. The 2400-cent cap is shared by all lines with
    the same account_id (across its subscriptions); distinct accounts have
    independent caps. Within a cap group, credit goes to the earliest service_on
    first, ties broken by increasing line_id (code-point order).
    """
    credits = {}
    remaining_by_account = {}
    for line in sorted(lines, key=lambda item: (item["service_on"], item["line_id"])):
        account = line["account_id"]
        remaining = remaining_by_account.get(account, ACCOUNT_CAP_CENTS)
        credit = min(uncapped_credit(line["charge_cents"]), remaining)
        remaining_by_account[account] = remaining - credit
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
    credit = assign_credits([line])[line["line_id"]]
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
