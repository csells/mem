#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "1.0"
ACCOUNT_CREDIT_CAP_CENTS = 2400


def statement_credits(lines):
    """Return assigned release 1.0 credits keyed by line ID."""
    credits = {}
    lines_by_account = {}

    for line in lines:
        lines_by_account.setdefault(line["account_id"], []).append(line)

    for account_lines in lines_by_account.values():
        remaining_credit = ACCOUNT_CREDIT_CAP_CENTS
        for line in sorted(
            account_lines, key=lambda item: (item["service_on"], item["line_id"])
        ):
            uncapped_credit = line["charge_cents"] // 10
            assigned_credit = min(uncapped_credit, remaining_credit)
            credits[line["line_id"]] = assigned_credit
            remaining_credit -= assigned_credit

    return credits


def quote(line):
    credit_cents = statement_credits([line])[line["line_id"]]
    return {
        "release": CURRENT_RELEASE,
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
        "line_id": line["line_id"],
    }


def total(lines):
    credits = statement_credits(lines)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": CURRENT_RELEASE,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote(request["line"])
    if command == "total":
        return total(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
