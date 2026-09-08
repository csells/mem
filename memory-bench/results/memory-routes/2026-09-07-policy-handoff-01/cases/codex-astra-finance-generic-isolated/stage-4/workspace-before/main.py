#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def statement_total(lines, release=CURRENT_RELEASE):
    rate, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
    credits_by_group = {}
    charge_cents = 0
    for line in lines:
        group = (line["account_id"] if release == "1.0" else
                 (line["account_id"], line["subscription_id"]))
        charge_cents += line["charge_cents"]
        credits_by_group[group] = (
            credits_by_group.get(group, 0) + line["charge_cents"] * rate // 100
        )
    # Allocation order affects individual credits, but not a cap group's total.
    # quote supplies one line, so neither response needs allocation sorting.
    credit_cents = sum(min(credit, cap) for credit in credits_by_group.values())
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        return {**statement_total([line], request.get("release", CURRENT_RELEASE)),
                "line_id": line["line_id"]}
    if request.get("command") == "total":
        return statement_total(request["lines"], request.get("release", CURRENT_RELEASE))
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
