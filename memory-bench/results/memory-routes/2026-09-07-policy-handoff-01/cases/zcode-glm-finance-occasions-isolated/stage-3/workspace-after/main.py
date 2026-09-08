#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CAP_CENTS_1_0 = 2400
CAP_CENTS_2_0 = 3000
CURRENT_RELEASE = "2.0"


def assign_credits_1_0(lines):
    """Release 1.0 credits for one statement's complete charge set: 10% of
    each charge rounded down to integer cents, with CAP_CENTS_1_0 shared by
    all lines of one account_id across its subscriptions. Within a cap group,
    credit goes to lines by earliest service_on, then increasing line_id."""
    assigned = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        left = remaining.setdefault(line["account_id"], CAP_CENTS_1_0)
        credit = min(line["charge_cents"] // 10, left)
        assigned[line["line_id"]] = credit
        remaining[line["account_id"]] = left - credit
    return assigned


def assign_credits_2_0(lines):
    """Release 2.0 credits for one statement's complete charge set: 15% of
    each charge rounded down separately to integer cents, with CAP_CENTS_2_0
    shared by all lines of one (account_id, subscription_id) pair. Within a
    cap group, credit goes to lines by largest charge_cents, then increasing
    line_id; each line receives its uncapped credit up to the remaining cap."""
    assigned = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (-l["charge_cents"], l["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        left = remaining.setdefault(group, CAP_CENTS_2_0)
        credit = min(line["charge_cents"] * 15 // 100, left)
        assigned[line["line_id"]] = credit
        remaining[group] = left - credit
    return assigned


def quote_1_0(line):
    credit = assign_credits_1_0([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_1_0(lines):
    credit = sum(assign_credits_1_0(lines).values())
    return {
        "release": "1.0",
        "credit_cents": credit,
        "amount_due_cents": sum(l["charge_cents"] for l in lines) - credit,
    }


def quote_2_0(line):
    credit = assign_credits_2_0([line])[line["line_id"]]
    return {
        "release": "2.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_2_0(lines):
    credit = sum(assign_credits_2_0(lines).values())
    return {
        "release": "2.0",
        "credit_cents": credit,
        "amount_due_cents": sum(l["charge_cents"] for l in lines) - credit,
    }


RELEASES = {"1.0": quote_1_0, "2.0": quote_2_0}
TOTALS = {"1.0": total_1_0, "2.0": total_2_0}


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", CURRENT_RELEASE)
        if release not in RELEASES:
            return {"error": "unsupported_release"}
        return RELEASES[release](request["line"])
    if command == "total":
        release = request.get("release", CURRENT_RELEASE)
        if release not in TOTALS:
            return {"error": "unsupported_release"}
        return TOTALS[release](request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
