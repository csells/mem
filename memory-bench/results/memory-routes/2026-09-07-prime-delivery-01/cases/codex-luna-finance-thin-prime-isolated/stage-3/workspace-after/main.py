#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"
RELEASE_1_RATE_DIVISOR = 10
RELEASE_1_CAP_CENTS = 2400
RELEASE_2_RATE_DIVISOR = 100
RELEASE_2_CAP_CENTS = 3000


def statement_credit(lines):
    """Return the release-1.0 credit assigned across a complete statement."""
    groups = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(line)

    total_credit = 0
    for group_lines in groups.values():
        remaining = RELEASE_1_CAP_CENTS
        ordered_lines = sorted(group_lines,
                               key=lambda line: (line["service_on"], line["line_id"]))
        for line in ordered_lines:
            credit_cents = min(line["charge_cents"] // RELEASE_1_RATE_DIVISOR,
                               remaining)
            total_credit += credit_cents
            remaining -= credit_cents
    return total_credit


def release_2_statement_credit(lines):
    """Return the release-2.0 credit assigned across a complete statement."""
    groups = {}
    for line in lines:
        groups.setdefault(line["account_id"], []).append(line)

    total_credit = 0
    for group_lines in groups.values():
        remaining = RELEASE_2_CAP_CENTS
        ordered_lines = sorted(group_lines,
                               key=lambda line: (-line["charge_cents"], line["line_id"]))
        for line in ordered_lines:
            credit_cents = min(line["charge_cents"] * 15 // RELEASE_2_RATE_DIVISOR,
                               remaining)
            total_credit += credit_cents
            remaining -= credit_cents
    return total_credit


def line_credit(line, release):
    """Return the credit for a one-line statement under the selected release."""
    if release == "1.0":
        return min(line["charge_cents"] // RELEASE_1_RATE_DIVISOR,
                   RELEASE_1_CAP_CENTS)
    return min(line["charge_cents"] * 15 // RELEASE_2_RATE_DIVISOR,
               RELEASE_2_CAP_CENTS)


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        release = request.get("release", CURRENT_RELEASE)
        credit_cents = line_credit(line, release)
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
            "line_id": line["line_id"],
        }
    if request.get("command") == "total":
        lines = request["lines"]
        release = request.get("release", CURRENT_RELEASE)
        total_charge = sum(line["charge_cents"] for line in lines)
        credit_cents = (statement_credit(lines) if release == "1.0"
                        else release_2_statement_credit(lines))
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": total_charge - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
