#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"
ACCOUNT_CAP_CENTS = 2400


def assign_credits_1_0(lines):
    """Credit cents assigned to each line of a complete statement, in input order.

    Uncapped credit is 10% of charge_cents rounded down per line. The cap is
    shared per account_id across subscriptions; within a group, lines are
    served by earliest service_on, then increasing line_id.
    """
    credits = [0] * len(lines)
    by_account = {}
    for idx, line in enumerate(lines):
        by_account.setdefault(line["account_id"], []).append(idx)
    for indexes in by_account.values():
        remaining = ACCOUNT_CAP_CENTS
        order = sorted(indexes, key=lambda i: (lines[i]["service_on"], lines[i]["line_id"]))
        for i in order:
            credit = min(lines[i]["charge_cents"] // 10, remaining)
            credits[i] = credit
            remaining -= credit
    return credits


def quote_1_0(line):
    credit = assign_credits_1_0([line])[0]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_1_0(lines):
    credits = assign_credits_1_0(lines)
    credit_cents = sum(credits)
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": sum(line["charge_cents"] for line in lines) - credit_cents,
    }


QUOTERS = {
    "1.0": quote_1_0,
}

TOTALERS = {
    "1.0": total_1_0,
}


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", CURRENT_RELEASE)
        if release not in QUOTERS:
            return {"error": "unsupported_release"}
        return QUOTERS[release](request["line"])
    if request.get("command") == "total":
        release = request.get("release", CURRENT_RELEASE)
        if release not in TOTALERS:
            return {"error": "unsupported_release"}
        return TOTALERS[release](request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
