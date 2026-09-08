#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE = "1.0"
CREDIT_CAP_CENTS = 2400


def assigned_credits(lines):
    """Return each line's credit after applying its subscription cap."""
    credits = [0] * len(lines)
    groups = {}
    for index, line in enumerate(lines):
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(index)

    for group in groups.values():
        remaining = CREDIT_CAP_CENTS
        for index in sorted(group, key=lambda i: (lines[i]["service_on"], lines[i]["line_id"])):
            credit = min(lines[index]["charge_cents"] // 10, remaining)
            credits[index] = credit
            remaining -= credit

    return credits


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        credit_cents = assigned_credits([line])[0]
        return {
            "release": RELEASE,
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
            "line_id": line["line_id"],
        }
    if request.get("command") == "total":
        lines = request["lines"]
        credit_cents = sum(assigned_credits(lines))
        total_cents = sum(line["charge_cents"] for line in lines)
        return {
            "release": RELEASE,
            "credit_cents": credit_cents,
            "amount_due_cents": total_cents - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
