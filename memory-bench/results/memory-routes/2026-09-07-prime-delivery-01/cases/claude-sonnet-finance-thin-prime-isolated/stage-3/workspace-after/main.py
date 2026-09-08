#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"

RELEASE_1_CAP_CENTS = 2400
RELEASE_2_CAP_CENTS = 3000


def assign_credits_1_0(lines):
    """Map line_id -> assigned credit_cents per the release 1.0 cap agreement."""
    groups = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=lambda l: (l["service_on"], l["line_id"]))
        remaining = RELEASE_1_CAP_CENTS
        for line in group_lines:
            uncapped = line["charge_cents"] * 10 // 100
            assigned = min(uncapped, remaining)
            credits[line["line_id"]] = assigned
            remaining -= assigned
    return credits


def assign_credits_2_0(lines):
    """Map line_id -> assigned credit_cents per the release 2.0 cap agreement."""
    groups = {}
    for line in lines:
        groups.setdefault(line["account_id"], []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=lambda l: (-l["charge_cents"], l["line_id"]))
        remaining = RELEASE_2_CAP_CENTS
        for line in group_lines:
            uncapped = line["charge_cents"] * 15 // 100
            assigned = min(uncapped, remaining)
            credits[line["line_id"]] = assigned
            remaining -= assigned
    return credits


ASSIGN_CREDITS_BY_RELEASE = {
    "1.0": assign_credits_1_0,
    "2.0": assign_credits_2_0,
}


def resolve_release(request):
    return request.get("release", CURRENT_RELEASE)


def quote_line(line, release):
    charge_cents = line["charge_cents"]
    credit_cents = ASSIGN_CREDITS_BY_RELEASE[release]([line])[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def total_statement(lines, release):
    credits = ASSIGN_CREDITS_BY_RELEASE[release](lines)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"], resolve_release(request))
    if command == "total":
        return total_statement(request["lines"], resolve_release(request))
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
