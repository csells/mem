#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CREDIT_CAP_CENTS = 2400


def assign_credits(lines):
    """Return {line_id: credit_cents} applying the per-subscription cap."""
    groups = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=lambda line: (line["service_on"], line["line_id"]))
        remaining_cap = CREDIT_CAP_CENTS
        for line in group_lines:
            uncapped = line["charge_cents"] * 10 // 100
            credit = min(uncapped, remaining_cap)
            credits[line["line_id"]] = credit
            remaining_cap -= credit
    return credits


def quote_line(line):
    credit_cents = assign_credits([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def total_statement(lines):
    credits = assign_credits(lines)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"])
    if command == "total":
        return total_statement(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
