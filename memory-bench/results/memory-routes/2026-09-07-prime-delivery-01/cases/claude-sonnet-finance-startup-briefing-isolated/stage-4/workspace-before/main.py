#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys

CREDIT_CAP_CENTS_R1 = 2400
CREDIT_CAP_CENTS_R2 = 3000


def credit_for_charge_r1(charge_cents):
    return min(charge_cents * 10 // 100, CREDIT_CAP_CENTS_R1)


def quote_line_r1(line):
    charge_cents = line["charge_cents"]
    credit_cents = credit_for_charge_r1(charge_cents)
    return {
        "release": "1.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def quote_total_r1(lines):
    subscription_charges = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        subscription_charges[key] = subscription_charges.get(key, 0) + line["charge_cents"]
    total_charge_cents = sum(subscription_charges.values())
    credit_cents = sum(credit_for_charge_r1(c) for c in subscription_charges.values())
    return {
        "release": "1.0",
        "credit_cents": credit_cents,
        "amount_due_cents": total_charge_cents - credit_cents,
    }


def assign_credits_r2(lines):
    """Return {line_id: credit_cents} per the release 2.0 per-account cap."""
    by_account = {}
    for line in lines:
        by_account.setdefault(line["account_id"], []).append(line)
    credits = {}
    for account_lines in by_account.values():
        account_lines.sort(key=lambda l: (-l["charge_cents"], l["line_id"]))
        remaining_cap = CREDIT_CAP_CENTS_R2
        for line in account_lines:
            uncapped = line["charge_cents"] * 15 // 100
            assigned = min(uncapped, remaining_cap)
            credits[line["line_id"]] = assigned
            remaining_cap -= assigned
    return credits


def quote_line_r2(line):
    credit_cents = assign_credits_r2([line])[line["line_id"]]
    return {
        "release": "2.0",
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": line["charge_cents"] - credit_cents,
    }


def quote_total_r2(lines):
    credits = assign_credits_r2(lines)
    total_charge_cents = sum(line["charge_cents"] for line in lines)
    credit_cents = sum(credits.values())
    return {
        "release": "2.0",
        "credit_cents": credit_cents,
        "amount_due_cents": total_charge_cents - credit_cents,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    release = request.get("release", "2.0")
    if command == "quote":
        return quote_line_r1(request["line"]) if release == "1.0" else quote_line_r2(request["line"])
    if command == "total":
        return quote_total_r1(request["lines"]) if release == "1.0" else quote_total_r2(request["lines"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
