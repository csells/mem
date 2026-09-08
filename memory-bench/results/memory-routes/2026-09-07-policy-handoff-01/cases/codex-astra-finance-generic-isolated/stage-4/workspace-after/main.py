#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def statement_total(lines, release=CURRENT_RELEASE):
    rate, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
    credits_by_group = {}
    charge_cents = 0
    for line in lines:
        group = (line["account_id"] if release == "1.0" else
                 (line["account_id"], line["subscription_id"]))
        charge_cents += line["charge_cents"]
        credits_by_group[group] = (
            credits_by_group.get(group, 0) + line["charge_cents"] * rate // 100
        )
    # Allocation order affects individual credits, but not a cap group's total.
    # quote supplies one line, so neither response needs allocation sorting.
    credit_cents = sum(min(credit, cap) for credit in credits_by_group.values())
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def statement(lines):
    remaining_by_group = {}
    credits_by_line = {}
    for line in sorted(lines, key=lambda line: (-line["charge_cents"], line["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        remaining = remaining_by_group.get(group, 3000)
        credit = min(line["charge_cents"] * 15 // 100, remaining)
        credits_by_line[line["line_id"]] = credit
        remaining_by_group[group] = remaining - credit

    response_lines = [
        {"line_id": line["line_id"],
         "credit_cents": credits_by_line[line["line_id"]],
         "amount_due_cents": line["charge_cents"] - credits_by_line[line["line_id"]]}
        for line in lines
    ]
    return {
        "release": CURRENT_RELEASE,
        "lines": response_lines,
        "credit_cents": sum(line["credit_cents"] for line in response_lines),
        "amount_due_cents": sum(line["amount_due_cents"] for line in response_lines),
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        return {**statement_total([line], request.get("release", CURRENT_RELEASE)),
                "line_id": line["line_id"]}
    if request.get("command") == "total":
        return statement_total(request["lines"], request.get("release", CURRENT_RELEASE))
    if request.get("command") == "statement":
        return statement(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
