#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"

RELEASE_1_0_CREDIT_CAP_CENTS = 2400
RELEASE_2_0_CREDIT_CAP_CENTS = 3000


def assign_credits_1_0(lines):
    """Return {line_id: credit_cents} honoring the per-(account_id, subscription_id) cap."""
    groups = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=lambda line: (line["service_on"], line["line_id"]))
        remaining = RELEASE_1_0_CREDIT_CAP_CENTS
        for line in group_lines:
            uncapped = line["charge_cents"] * 10 // 100
            credit = min(uncapped, remaining)
            credits[line["line_id"]] = credit
            remaining -= credit
    return credits


def assign_credits_2_0(lines):
    """Return {line_id: credit_cents} honoring the per-account_id cap."""
    groups = {}
    for line in lines:
        groups.setdefault(line["account_id"], []).append(line)

    credits = {}
    for group_lines in groups.values():
        group_lines.sort(key=lambda line: (-line["charge_cents"], line["line_id"]))
        remaining = RELEASE_2_0_CREDIT_CAP_CENTS
        for line in group_lines:
            uncapped = line["charge_cents"] * 15 // 100
            credit = min(uncapped, remaining)
            credits[line["line_id"]] = credit
            remaining -= credit
    return credits


RELEASES = {
    "1.0": assign_credits_1_0,
    "2.0": assign_credits_2_0,
}


def resolve_release(request):
    return request.get("release", CURRENT_RELEASE)


def quote_line(release, line):
    credit_cents = RELEASES[release]([line])[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def quote_total(release, lines):
    credits = RELEASES[release](lines)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def quote_statement(release, lines):
    credits = RELEASES[release](lines)
    credit_cents = sum(credits.values())
    charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
        "lines": [
            {
                "line_id": line["line_id"],
                "credit_cents": credits[line["line_id"]],
                "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
            }
            for line in lines
        ],
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(resolve_release(request), request["line"])
    if command == "total":
        return quote_total(resolve_release(request), request["lines"])
    if command == "statement":
        return quote_statement(resolve_release(request), request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
