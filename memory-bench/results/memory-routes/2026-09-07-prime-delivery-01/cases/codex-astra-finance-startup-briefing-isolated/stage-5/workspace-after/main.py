#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        charge = line["charge_cents"]
        credit = min(charge // 10, 2400)
        return {
            "release": "1.0",
            "line_id": line["line_id"],
            "credit_cents": credit,
            "amount_due_cents": charge - credit,
        }
    if request.get("command") == "total":
        total_charge = 0
        account_credits = {}
        for line in request["lines"]:
            charge = line["charge_cents"]
            account = line["account_id"]
            total_charge += charge
            account_credits[account] = account_credits.get(account, 0) + charge // 10
        # Allocation order affects individual lines, but each account's total
        # is its summed, separately rounded credits limited by the shared cap.
        credit = sum(min(uncapped, 2400) for uncapped in account_credits.values())
        return {
            "release": "1.0",
            "credit_cents": credit,
            "amount_due_cents": total_charge - credit,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
