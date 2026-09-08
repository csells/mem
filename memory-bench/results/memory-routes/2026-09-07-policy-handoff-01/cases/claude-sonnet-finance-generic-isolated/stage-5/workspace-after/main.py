#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"

RELEASE_AGREEMENTS = {
    "1.0": {
        "rate_percent": 10,
        "cap_cents": 2400,
        "group_key": lambda line: (line["account_id"], line["subscription_id"]),
        "priority_key": lambda line: (line["service_on"], line["line_id"]),
    },
    "2.0": {
        "rate_percent": 15,
        "cap_cents": 3000,
        "group_key": lambda line: line["account_id"],
        "priority_key": lambda line: (-line["charge_cents"], line["line_id"]),
    },
}


def assign_credits(lines, release):
    """Return {line_id: credit_cents} applying the release's shared cap."""
    agreement = RELEASE_AGREEMENTS[release]
    groups = {}
    for line in lines:
        key = agreement["group_key"](line)
        groups.setdefault(key, []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=agreement["priority_key"])
        remaining_cap = agreement["cap_cents"]
        for line in group_lines:
            uncapped = line["charge_cents"] * agreement["rate_percent"] // 100
            credit = min(uncapped, remaining_cap)
            credits[line["line_id"]] = credit
            remaining_cap -= credit
    return credits


def quote_line(line, release):
    credit_cents = assign_credits([line], release)[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def total_statement(lines, release):
    credits = assign_credits(lines, release)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def statement(lines, release):
    credits = assign_credits(lines, release)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    response_lines = [
        {
            "line_id": line["line_id"],
            "credit_cents": credits[line["line_id"]],
            "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
        }
        for line in lines
    ]
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
        "lines": response_lines,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", CURRENT_RELEASE)
        return quote_line(request["line"], release)
    if command == "total":
        release = request.get("release", CURRENT_RELEASE)
        return total_statement(request["lines"], release)
    if command == "statement":
        release = request.get("release", CURRENT_RELEASE)
        return statement(request["lines"], release)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
