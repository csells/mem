#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"
SUPPORTED_RELEASES = ("1.0",)

CAP_CENTS_PER_ACCOUNT = 2400


def assign_credits(lines):
    """Release 1.0 agreement: each line earns 10% of its charge floored to
    integer cents; the 2400-cent cap is shared by all lines of one account_id,
    assigned earliest service_on first, then increasing line_id. Returns
    {line_id: assigned_credit_cents}."""
    remaining = {}
    for line in lines:
        remaining.setdefault(line["account_id"], CAP_CENTS_PER_ACCOUNT)
    assigned = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        uncapped = line["charge_cents"] // 10
        credit = min(uncapped, remaining[line["account_id"]])
        remaining[line["account_id"]] -= credit
        assigned[line["line_id"]] = credit
    return assigned


def quote_release_1_0(line):
    credit = assign_credits([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def quote(request):
    release = request.get("release", CURRENT_RELEASE)
    if release not in SUPPORTED_RELEASES:
        return {"error": "unsupported_release"}
    return quote_release_1_0(request["line"])


def total_release_1_0(lines):
    assigned = assign_credits(lines)
    credit = sum(assigned.values())
    charge = sum(line["charge_cents"] for line in lines)
    return {
        "release": "1.0",
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def total(request):
    release = request.get("release", CURRENT_RELEASE)
    if release not in SUPPORTED_RELEASES:
        return {"error": "unsupported_release"}
    return total_release_1_0(request["lines"])


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        return quote(request)
    if request.get("command") == "total":
        return total(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
