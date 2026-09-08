#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CAP_CENTS = 2400
CURRENT_RELEASE = "1.0"


def assign_credits_1_0(lines):
    """Release 1.0 credits for one statement's complete charge set: 10% of
    each charge rounded down to integer cents, with CAP_CENTS shared by all
    lines of one account_id across its subscriptions. Within a cap group,
    credit goes to lines by earliest service_on, then increasing line_id."""
    assigned = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        left = remaining.setdefault(line["account_id"], CAP_CENTS)
        credit = min(line["charge_cents"] // 10, left)
        assigned[line["line_id"]] = credit
        remaining[line["account_id"]] = left - credit
    return assigned


def quote_1_0(line):
    credit = assign_credits_1_0([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


RELEASES = {"1.0": quote_1_0}


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", CURRENT_RELEASE)
        if release not in RELEASES:
            return {"error": "unsupported_release"}
        return RELEASES[release](request["line"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
