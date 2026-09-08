#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def statement_total(lines):
    credits_by_account = {}
    charge_cents = 0
    for line in lines:
        account_id = line["account_id"]
        charge_cents += line["charge_cents"]
        credits_by_account[account_id] = (
            credits_by_account.get(account_id, 0) + line["charge_cents"] // 10
        )
    # Allocation order affects individual credits, but not the account total.
    credit_cents = sum(min(credit, 2400) for credit in credits_by_account.values())
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        return {**statement_total([line]), "line_id": line["line_id"]}
    if request.get("command") == "total":
        return statement_total(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
