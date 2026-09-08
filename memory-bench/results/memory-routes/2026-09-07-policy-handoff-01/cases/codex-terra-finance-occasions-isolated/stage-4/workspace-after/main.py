#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_0 = "1.0"
RELEASE_2_0 = "2.0"
CURRENT_RELEASE = RELEASE_2_0


def quote_line(line, release):
    """Quote one charge line as a complete, one-line statement."""
    credit_cents = allocated_credits([line], release)[line["line_id"]]
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def allocated_credits(lines, release):
    """Allocate shared credit caps according to the selected agreement."""
    lines_by_cap_group = {}
    for line in lines:
        if release == RELEASE_1_0:
            cap_group = (line["account_id"], line["subscription_id"])
        else:
            cap_group = line["account_id"]
        lines_by_cap_group.setdefault(cap_group, []).append(line)

    credits = {}
    for group_lines in lines_by_cap_group.values():
        if release == RELEASE_1_0:
            cap_cents = 2400
            ordered_lines = sorted(group_lines, key=lambda item: (item["service_on"], item["line_id"]))
            uncapped_credit = lambda line: line["charge_cents"] * 10 // 100
        else:
            cap_cents = 3000
            ordered_lines = sorted(group_lines, key=lambda item: (-item["charge_cents"], item["line_id"]))
            uncapped_credit = lambda line: line["charge_cents"] * 15 // 100

        remaining_credit = cap_cents
        for line in ordered_lines:
            credit_cents = min(uncapped_credit(line), remaining_credit)
            credits[line["line_id"]] = credit_cents
            remaining_credit -= credit_cents
    return credits


def total_statement(lines, release):
    """Quote the supplied complete monthly statement under the selected agreement."""
    credits = allocated_credits(lines, release)
    total_credit_cents = sum(credits.values())
    total_charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": total_credit_cents,
        "amount_due_cents": total_charge_cents - total_credit_cents,
    }


def statement(lines):
    """Show allocated credit and amount due for every supplied charge line."""
    credits = allocated_credits(lines, RELEASE_2_0)
    total_credit_cents = sum(credits.values())
    total_charge_cents = sum(line["charge_cents"] for line in lines)
    return {
        "release": RELEASE_2_0,
        "lines": [
            {
                "line_id": line["line_id"],
                "credit_cents": credits[line["line_id"]],
                "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
            }
            for line in lines
        ],
        "credit_cents": total_credit_cents,
        "amount_due_cents": total_charge_cents - total_credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    release = request.get("release", CURRENT_RELEASE)
    if request.get("command") == "quote" and release in (RELEASE_1_0, RELEASE_2_0):
        return quote_line(request["line"], release)
    if request.get("command") == "total" and release in (RELEASE_1_0, RELEASE_2_0):
        return total_statement(request["lines"], release)
    if request.get("command") == "statement" and release == RELEASE_2_0:
        return statement(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
