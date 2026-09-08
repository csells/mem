#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"

CAP_CENTS_1_0 = 2400
CREDIT_DIVISOR_1_0 = 10


def assigned_credit_cents_1_0(lines):
    """Release 1.0: each line earns floor(10% of charge), assigned within a
    2400-cent cap shared per account_id, earliest service_on first then
    increasing line_id."""
    credits = {}
    remaining = {}
    ordered = sorted(lines, key=lambda line: (line["service_on"], line["line_id"]))
    for line in ordered:
        uncapped = line["charge_cents"] // CREDIT_DIVISOR_1_0
        cap_left = remaining.setdefault(line["account_id"], CAP_CENTS_1_0)
        credit = min(uncapped, cap_left)
        remaining[line["account_id"]] = cap_left - credit
        credits[line["line_id"]] = credit
    return credits


def quote_1_0(line):
    credit = assigned_credit_cents_1_0([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_1_0(lines):
    credit_cents = sum(assigned_credit_cents_1_0(lines).values())
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": sum(line["charge_cents"] for line in lines) - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", CURRENT_RELEASE)
        if release == "1.0":
            return quote_1_0(request["line"])
        return {"error": "unsupported_release"}
    if command == "total":
        release = request.get("release", CURRENT_RELEASE)
        if release == "1.0":
            return total_1_0(request["lines"])
        return {"error": "unsupported_release"}
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
