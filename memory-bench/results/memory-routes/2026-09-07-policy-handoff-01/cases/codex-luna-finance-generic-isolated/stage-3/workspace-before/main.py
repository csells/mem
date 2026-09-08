#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def assigned_credits(lines):
    """Return each line's release 1.0 credit after group caps are applied."""
    credits = {}
    groups = {}
    for line in lines:
        group = (line["account_id"], line["subscription_id"])
        groups.setdefault(group, []).append(line)

    for group_lines in groups.values():
        remaining = 2400
        for line in sorted(group_lines, key=lambda item: (item["service_on"], item["line_id"])):
            uncapped = line["charge_cents"] * 10 // 100
            credit = min(uncapped, remaining)
            credits[line["line_id"]] = credit
            remaining -= credit
    return credits


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        credit_cents = assigned_credits([line])[line["line_id"]]
        return {
            "release": request.get("release", "1.0"),
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total":
        lines = request["lines"]
        credits = assigned_credits(lines)
        credit_cents = sum(credits[line["line_id"]] for line in lines)
        charge_cents = sum(line["charge_cents"] for line in lines)
        return {
            "release": request.get("release", "1.0"),
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
