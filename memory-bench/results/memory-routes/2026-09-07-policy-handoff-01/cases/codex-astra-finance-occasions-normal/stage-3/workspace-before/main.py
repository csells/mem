#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        credit_cents = min(line["charge_cents"] // 10, 2400)
        return {
            "release": "1.0",
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total":
        account_credits = {}
        charge_cents = 0
        for line in request["lines"]:
            account_id = line["account_id"]
            account_credits[account_id] = (
                account_credits.get(account_id, 0) + line["charge_cents"] // 10
            )
            charge_cents += line["charge_cents"]
        # Allocation priority affects individual lines, but not account totals.
        credit_cents = sum(min(credit, 2400) for credit in account_credits.values())
        return {
            "release": "1.0",
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
