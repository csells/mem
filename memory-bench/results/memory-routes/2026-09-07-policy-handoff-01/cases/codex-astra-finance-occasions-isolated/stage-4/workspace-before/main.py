#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def statement_credit(lines, release):
    rate, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
    group_credits = {}
    for line in lines:
        group = line["account_id"]
        if release == "2.0":
            group = (group, line["subscription_id"])
        group_credits[group] = (
            group_credits.get(group, 0) + line["charge_cents"] * rate // 100
        )
    # Priority changes individual allocations, but not the capped group total.
    return sum(min(credit, cap) for credit in group_credits.values())


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", CURRENT_RELEASE)
        line = request["line"]
        credit_cents = statement_credit([line], release)
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total":
        release = request.get("release", CURRENT_RELEASE)
        charge_cents = sum(line["charge_cents"] for line in request["lines"])
        credit_cents = statement_credit(request["lines"], release)
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
