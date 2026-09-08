#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def assigned_credits(lines, release):
    """Return assigned credits for the requested agreement."""
    credits = {}
    groups = {}
    for line in lines:
        if release == "1.0":
            group = (line["account_id"], line["subscription_id"])
        else:
            group = line["account_id"]
        groups.setdefault(group, []).append(line)

    for group_lines in groups.values():
        remaining = 2400 if release == "1.0" else 3000
        if release == "1.0":
            priority = lambda item: (item["service_on"], item["line_id"])
            rate = 10
        else:
            priority = lambda item: (-item["charge_cents"], item["line_id"])
            rate = 15
        for line in sorted(group_lines, key=priority):
            uncapped = line["charge_cents"] * rate // 100
            credit = min(uncapped, remaining)
            credits[line["line_id"]] = credit
            remaining -= credit
    return credits


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        release = request.get("release", CURRENT_RELEASE)
        credit_cents = assigned_credits([line], release)[line["line_id"]]
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total":
        lines = request["lines"]
        release = request.get("release", CURRENT_RELEASE)
        credits = assigned_credits(lines, release)
        credit_cents = sum(credits[line["line_id"]] for line in lines)
        charge_cents = sum(line["charge_cents"] for line in lines)
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
