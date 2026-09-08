#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys
from typing import Callable, NamedTuple


class Agreement(NamedTuple):
    """One approved credit agreement.

    credit_percent of a charge, rounded down separately per line, is a line's
    uncapped credit. Lines sharing a cap group draw on one cap_cents pool in
    priority order; distinct groups have independent caps.
    """
    credit_percent: int
    cap_cents: int
    group: Callable
    priority: Callable


AGREEMENTS = {
    # Release 1.0: 10% per line, cap shared per subscription, earliest service
    # date first and, for equal dates, increasing line_id.
    "1.0": Agreement(
        credit_percent=10,
        cap_cents=2400,
        group=lambda line: (line["account_id"], line["subscription_id"]),
        priority=lambda line: (line["service_on"], line["line_id"]),
    ),
    # Release 2.0: 15% per line, cap shared per account across its
    # subscriptions, largest charge first and, for equal charges, increasing
    # line_id.
    "2.0": Agreement(
        credit_percent=15,
        cap_cents=3000,
        group=lambda line: line["account_id"],
        priority=lambda line: (-line["charge_cents"], line["line_id"]),
    ),
}
CURRENT_RELEASE = "2.0"


def assign_credits(lines, agreement):
    """Map line_id to the credit the agreement assigns that line."""
    remaining = {}
    credits = {}
    for line in sorted(lines, key=agreement.priority):
        group = agreement.group(line)
        available = remaining.get(group, agreement.cap_cents)
        uncapped = line["charge_cents"] * agreement.credit_percent // 100
        credit = min(uncapped, available)
        remaining[group] = available - credit
        credits[line["line_id"]] = credit
    return credits


def selected(request):
    """The release the request asks for, and its agreement."""
    release = request.get("release", CURRENT_RELEASE)
    return release, AGREEMENTS[release]


def quote(request):
    """Quote one charge line treated as an entire monthly statement."""
    release, agreement = selected(request)
    line = request["line"]
    credit = assign_credits([line], agreement)[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total(request):
    """Quote a whole monthly statement, sharing caps across its charge lines."""
    release, agreement = selected(request)
    lines = request["lines"]
    credit = sum(assign_credits(lines, agreement).values())
    charges = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": charges - credit,
    }


def statement(request):
    """Quote a whole monthly statement, itemizing the credit on every line."""
    release, agreement = selected(request)
    credits = assign_credits(request["lines"], agreement)
    lines = [{
        "line_id": line["line_id"],
        "credit_cents": credits[line["line_id"]],
        "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
    } for line in request["lines"]]
    return {
        "release": release,
        "lines": lines,
        "credit_cents": sum(line["credit_cents"] for line in lines),
        "amount_due_cents": sum(line["amount_due_cents"] for line in lines),
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote(request)
    if command == "total":
        return total(request)
    if command == "statement":
        return statement(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
