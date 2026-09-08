#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_0 = "1.0"
RELEASE_2_0 = "2.0"
CURRENT_RELEASE = RELEASE_2_0
CAP_CENTS_1_0 = 2400
CAP_CENTS_2_0 = 3000


def assign_credits_1_0(lines):
    """Yield (line_id, credit_cents) for a statement's complete charge set.

    Release 1.0: each line's uncapped credit is 10% of its charge rounded
    down; the 2400-cent cap is shared by all lines of one account_id, assigned
    in order of earliest service_on, then increasing line_id.
    """
    remaining = {}
    for line in sorted(lines, key=lambda line: (line["service_on"], line["line_id"])):
        left = remaining.setdefault(line["account_id"], CAP_CENTS_1_0)
        credit = min(line["charge_cents"] // 10, left)
        remaining[line["account_id"]] = left - credit
        yield line["line_id"], credit


def assign_credits_2_0(lines):
    """Yield (line_id, credit_cents) for a statement's complete charge set.

    Release 2.0: each line's uncapped credit is 15% of its charge rounded
    down; the 3000-cent cap is shared by all lines of one (account_id,
    subscription_id) pair, assigned largest charge_cents first, ties by
    increasing line_id.
    """
    remaining = {}
    for line in sorted(lines, key=lambda line: (-line["charge_cents"], line["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        left = remaining.setdefault(group, CAP_CENTS_2_0)
        credit = min(line["charge_cents"] * 15 // 100, left)
        remaining[group] = left - credit
        yield line["line_id"], credit


def assign_credits(release, lines):
    if release == RELEASE_1_0:
        return assign_credits_1_0(lines)
    return assign_credits_2_0(lines)


def quote(request):
    release = request.get("release", CURRENT_RELEASE)
    credits = dict(assign_credits(release, [request["line"]]))
    line_id = request["line"]["line_id"]
    credit = credits[line_id]
    charge = request["line"]["charge_cents"]
    return {
        "release": release,
        "line_id": line_id,
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def total(request):
    release = request.get("release", CURRENT_RELEASE)
    credit_cents = sum(credit for _, credit in assign_credits(release, request["lines"]))
    charge_cents = sum(line["charge_cents"] for line in request["lines"])
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def statement(request):
    release = request.get("release", CURRENT_RELEASE)
    credits = dict(assign_credits(release, request["lines"]))
    response_lines = [
        {
            "line_id": line["line_id"],
            "credit_cents": credits[line["line_id"]],
            "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
        }
        for line in request["lines"]
    ]
    credit_cents = sum(line["credit_cents"] for line in response_lines)
    charge_cents = sum(line["charge_cents"] for line in request["lines"])
    return {
        "release": release,
        "lines": response_lines,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        return quote(request)
    if request.get("command") == "total":
        return total(request)
    if request.get("command") == "statement":
        return statement(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
