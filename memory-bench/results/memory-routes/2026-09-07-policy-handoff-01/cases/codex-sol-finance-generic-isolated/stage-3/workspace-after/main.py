#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CURRENT_RELEASE = "2.0"
RELEASE_1_ACCOUNT_CAP_CENTS = 2400
RELEASE_2_SUBSCRIPTION_CAP_CENTS = 3000


def release_1_line_credit(line):
    return line["charge_cents"] // 10


def release_2_line_credit(line):
    return line["charge_cents"] * 15 // 100


def quote_line(line, release):
    if release == "1.0":
        credit_cents = min(
            release_1_line_credit(line), RELEASE_1_ACCOUNT_CAP_CENTS
        )
    else:
        credit_cents = min(
            release_2_line_credit(line), RELEASE_2_SUBSCRIPTION_CAP_CENTS
        )
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def release_1_total_credit(lines):
    uncapped_credit_by_account = {}

    for line in lines:
        account_id = line["account_id"]
        uncapped_credit_by_account[account_id] = (
            uncapped_credit_by_account.get(account_id, 0)
            + release_1_line_credit(line)
        )

    return sum(
        min(uncapped_credit, RELEASE_1_ACCOUNT_CAP_CENTS)
        for uncapped_credit in uncapped_credit_by_account.values()
    )


def release_2_total_credit(lines):
    lines_by_subscription = {}

    for line in lines:
        subscription = (line["account_id"], line["subscription_id"])
        lines_by_subscription.setdefault(subscription, []).append(line)

    total_credit_cents = 0
    for subscription_lines in lines_by_subscription.values():
        remaining_cap_cents = RELEASE_2_SUBSCRIPTION_CAP_CENTS
        for line in sorted(
            subscription_lines,
            key=lambda item: (-item["charge_cents"], item["line_id"]),
        ):
            assigned_credit_cents = min(
                release_2_line_credit(line), remaining_cap_cents
            )
            total_credit_cents += assigned_credit_cents
            remaining_cap_cents -= assigned_credit_cents

    return total_credit_cents


def total_statement(lines, release):
    charges_cents = 0
    for line in lines:
        charges_cents += line["charge_cents"]

    if release == "1.0":
        credit_cents = release_1_total_credit(lines)
    else:
        credit_cents = release_2_total_credit(lines)
    return {
        "release": release,
        "credit_cents": credit_cents,
        "amount_due_cents": charges_cents - credit_cents,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", CURRENT_RELEASE)
        return quote_line(request["line"], release)
    if request.get("command") == "total":
        release = request.get("release", CURRENT_RELEASE)
        return total_statement(request["lines"], release)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
