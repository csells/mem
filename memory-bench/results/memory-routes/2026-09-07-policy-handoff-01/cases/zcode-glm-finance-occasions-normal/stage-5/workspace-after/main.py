#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CAP_CENTS_1_0 = 2400
CAP_CENTS_2_0 = 3000
CURRENT_RELEASE = "2.0"


def assign_credits_1_0(lines):
    """Assign each line its release 1.0 credit.

    Uncapped credit is 10% of charge_cents rounded down per line. The
    2400-cent cap is shared by all lines with the same account_id, assigned
    earliest service_on first, then increasing line_id.
    """
    credits = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (l["service_on"], l["line_id"])):
        cap_left = remaining.setdefault(line["account_id"], CAP_CENTS_1_0)
        credit = min(line["charge_cents"] // 10, cap_left)
        remaining[line["account_id"]] = cap_left - credit
        credits[line["line_id"]] = credit
    return credits


def quote_line_1_0(line):
    credit = assign_credits_1_0([line])[line["line_id"]]
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_1_0(lines):
    """Quote a complete monthly statement under release 1.0.

    The per-account cap spans every line in the statement, not each
    line independently.
    """
    credits = assign_credits_1_0(lines)
    credit = sum(credits.values())
    charge = sum(line["charge_cents"] for line in lines)
    return {
        "release": "1.0",
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def assign_credits_2_0(lines):
    """Assign each line its release 2.0 credit.

    Uncapped credit is 15% of charge_cents rounded down per line. The
    3000-cent cap is shared by all lines with the same (account_id,
    subscription_id) pair, assigned largest charge_cents first, then
    increasing line_id.
    """
    credits = {}
    remaining = {}
    for line in sorted(lines, key=lambda l: (-l["charge_cents"], l["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        cap_left = remaining.setdefault(group, CAP_CENTS_2_0)
        credit = min(line["charge_cents"] * 15 // 100, cap_left)
        remaining[group] = cap_left - credit
        credits[line["line_id"]] = credit
    return credits


def quote_line_2_0(line):
    credit = assign_credits_2_0([line])[line["line_id"]]
    return {
        "release": "2.0",
        "line_id": line["line_id"],
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
    }


def total_2_0(lines):
    """Quote a complete monthly statement under release 2.0.

    The per-(account_id, subscription_id) cap spans every line in the
    statement, not each line independently.
    """
    credits = assign_credits_2_0(lines)
    credit = sum(credits.values())
    charge = sum(line["charge_cents"] for line in lines)
    return {
        "release": "2.0",
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def build_statement(release, assign_credits, lines):
    """Itemize a statement's per-line credit, preserving input line order.

    Overall amounts equal the total command for the same lines.
    """
    credits = assign_credits(lines)
    credit = sum(credits.values())
    charge = sum(line["charge_cents"] for line in lines)
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
        "credit_cents": credit,
        "amount_due_cents": charge - credit,
    }


def statement_1_0(lines):
    """Show the credit assigned to every line under release 1.0."""
    return build_statement("1.0", assign_credits_1_0, lines)


def statement_2_0(lines):
    """Show the credit assigned to every line under release 2.0."""
    return build_statement("2.0", assign_credits_2_0, lines)


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        release = request.get("release", CURRENT_RELEASE)
        if release == "1.0":
            return quote_line_1_0(request["line"])
        if release == "2.0":
            return quote_line_2_0(request["line"])
        return {"error": "unsupported_release"}
    if command == "total":
        release = request.get("release", CURRENT_RELEASE)
        if release == "1.0":
            return total_1_0(request["lines"])
        if release == "2.0":
            return total_2_0(request["lines"])
        return {"error": "unsupported_release"}
    if command == "statement":
        release = request.get("release", CURRENT_RELEASE)
        if release == "1.0":
            return statement_1_0(request["lines"])
        if release == "2.0":
            return statement_2_0(request["lines"])
        return {"error": "unsupported_release"}
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
