#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def credit_for_lines(lines, release):
    """Assign credits to a complete monthly statement under *release*."""
    if release == "1.0":
        cap = 2400

        def group_key(line):
            return (line["account_id"], line["subscription_id"])

        def priority(line):
            return (line["service_on"], line["line_id"])

        percentage = 10
    else:
        cap = 3000

        def group_key(line):
            return line["account_id"]

        def priority(line):
            return (-line["charge_cents"], line["line_id"])

        percentage = 15

    by_group = {}
    for line in lines:
        by_group.setdefault(group_key(line), []).append(line)

    credits = {}
    for group_lines in by_group.values():
        remaining = cap
        for line in sorted(group_lines, key=priority):
            uncapped = line["charge_cents"] * percentage // 100
            credit = min(uncapped, remaining)
            credits[line["line_id"]] = credit
            remaining -= credit
    return credits


def quote(line, release):
    credit = credit_for_lines([line], release)[line["line_id"]]
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
        "line_id": line["line_id"],
    }


def total(lines, release):
    credits = credit_for_lines(lines, release)
    total_credit = sum(credits.values())
    return {
        "release": release,
        "credit_cents": total_credit,
        "amount_due_cents": sum(line["charge_cents"] for line in lines) - total_credit,
    }


def statement(lines, release):
    credits = credit_for_lines(lines, release)
    total_credit = sum(credits.values())
    return {
        "release": release,
        "lines": [
            {
                "line_id": line["line_id"],
                "credit_cents": credits[line["line_id"]],
                "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
            }
            for line in lines
        ],
        "credit_cents": total_credit,
        "amount_due_cents": sum(line["charge_cents"] for line in lines) - total_credit,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command in {"quote", "total", "statement"}:
        release = request.get("release", CURRENT_RELEASE)
        supported_releases = {"1.0", "2.0"}
        if release not in supported_releases:
            return {"error": "unknown_release"}
        if command == "quote":
            return quote(request["line"], release)
        if command == "total":
            return total(request["lines"], release)
        return statement(request["lines"], release)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
