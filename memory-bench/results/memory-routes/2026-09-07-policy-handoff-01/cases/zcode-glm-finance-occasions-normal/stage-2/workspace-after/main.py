#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CAP_CENTS_1_0 = 2400


def assign_credits_1_0(lines):
    """Assign each line its release 1.0 credit.

    Uncapped credit is 10% of charge_cents rounded down per line. The
    2400-cent cap is shared by all lines with the same account_id, assigned
    earliest service_on first, then increasing line_id.
    """
    credits = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        cap_left = remaining.setdefault(line["account_id"], CAP_CENTS_1_0)
        credit = min(line["charge_cents"] // 10, cap_left)
        remaining[line["account_id"]] = cap_left - credit
        credits[line["line_id"]] = credit
    return credits


def quote_line_1_0(line):
    credit = assign_credits_1_0([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_1_0(lines):
    """Quote a complete monthly statement under release 1.0.

    The per-account cap spans every line in the statement, not each
    line independently.
    """
    credits = assign_credits_1_0(lines)
    credit = sum(credits.values())
    charge = sum(line["charge_cents"] for line in lines)
    return {
        "release": "1.0",
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", "1.0")
        if release != "1.0":
            return {"error": "unsupported_release"}
        return quote_line_1_0(request["line"])
    if command == "total":
        release = request.get("release", "1.0")
        if release != "1.0":
            return {"error": "unsupported_release"}
        return total_1_0(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
