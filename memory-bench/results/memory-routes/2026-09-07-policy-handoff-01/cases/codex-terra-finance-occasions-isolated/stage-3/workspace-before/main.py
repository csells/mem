#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_0 = "1.0"
SUBSCRIPTION_CREDIT_CAP_CENTS = 2400


def quote_line(line):
    """Quote one charge line as a complete, one-line statement."""
    credit_cents = allocated_credits([line])[line["line_id"]]
    return {
        "release": RELEASE_1_0,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def allocated_credits(lines):
    """Allocate each subscription's shared credit cap across its charge lines."""
    lines_by_subscription = {}
    for line in lines:
        subscription = (line["account_id"], line["subscription_id"])
        lines_by_subscription.setdefault(subscription, []).append(line)

    credits = {}
    for subscription_lines in lines_by_subscription.values():
        remaining_credit = SUBSCRIPTION_CREDIT_CAP_CENTS
        for line in sorted(subscription_lines, key=lambda item: (item["service_on"], item["line_id"])):
            credit_cents = min(line["charge_cents"] // 10, remaining_credit)
            credits[line["line_id"]] = credit_cents
            remaining_credit -= credit_cents
    return credits


def total_statement(lines):
    """Quote the supplied complete monthly statement under release 1.0."""
    credits = allocated_credits(lines)
    total_credit_cents = sum(credits.values())
    total_charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": RELEASE_1_0,
        "credit_cents": total_credit_cents,
        "amount_due_cents": total_charge_cents - total_credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote" and request.get("release", RELEASE_1_0) == RELEASE_1_0:
        return quote_line(request["line"])
    if request.get("command") == "total" and request.get("release", RELEASE_1_0) == RELEASE_1_0:
        return total_statement(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
