#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_0 = "1.0"
CURRENT_RELEASE = RELEASE_1_0
CAP_CENTS = 2400


def assign_credits(lines):
    """Yield (line_id, credit_cents) for a statement's complete charge set.

    Release 1.0: each line's uncapped credit is 10% of its charge rounded
    down; the 2400-cent cap is shared by all lines of one account_id, assigned
    in order of earliest service_on, then increasing line_id.
    """
    remaining = {}
    for line in sorted(lines, key=lambda line: (line["service_on"], line["line_id"])):
        left = remaining.setdefault(line["account_id"], CAP_CENTS)
        credit = min(line["charge_cents"] // 10, left)
        remaining[line["account_id"]] = left - credit
        yield line["line_id"], credit


def quote(request):
    release = request.get("release", CURRENT_RELEASE)
    credits = dict(assign_credits([request["line"]]))
    line_id = request["line"]["line_id"]
    credit = credits[line_id]
    charge = request["line"]["charge_cents"]
    return {
        "release": RELEASE_1_0,
        "line_id": line_id,
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        return quote(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
