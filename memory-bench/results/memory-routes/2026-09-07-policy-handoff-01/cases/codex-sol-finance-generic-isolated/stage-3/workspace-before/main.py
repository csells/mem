#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "1.0"
ACCOUNT_CREDIT_CAP_CENTS = 2400


def quote_line(line):
    credit_cents = min(line["charge_cents"] // 10, ACCOUNT_CREDIT_CAP_CENTS)
    return {
        "release": CURRENT_RELEASE,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def total_statement(lines):
    charges_cents = 0
    uncapped_credit_by_account = {}

    for line in lines:
        charges_cents += line["charge_cents"]
        account_id = line["account_id"]
        uncapped_credit_by_account[account_id] = (
            uncapped_credit_by_account.get(account_id, 0)
            + line["charge_cents"] // 10
        )

    credit_cents = sum(
        min(uncapped_credit, ACCOUNT_CREDIT_CAP_CENTS)
        for uncapped_credit in uncapped_credit_by_account.values()
    )
    return {
        "release": CURRENT_RELEASE,
        "credit_cents": credit_cents,
        "amount_due_cents": charges_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        return quote_line(request["line"])
    if request.get("command") == "total":
        return total_statement(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
