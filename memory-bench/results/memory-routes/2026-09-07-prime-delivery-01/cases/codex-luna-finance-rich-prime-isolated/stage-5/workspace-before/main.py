#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def assigned_credits_release_1(lines):
    """Return each line's credit using the original subscription cap."""
    credit_cap_cents = 2400
    credits = [0] * len(lines)
    groups = {}
    for index, line in enumerate(lines):
        key = (line["account_id"], line["subscription_id"])
        groups.setdefault(key, []).append(index)

    for group in groups.values():
        remaining = credit_cap_cents
        for index in sorted(group, key=lambda i: (lines[i]["service_on"], lines[i]["line_id"])):
            credit = min(lines[index]["charge_cents"] // 10, remaining)
            credits[index] = credit
            remaining -= credit

    return credits


def assigned_credits_release_2(lines):
    """Return each line's credit using the account-wide cap and priority."""
    credit_cap_cents = 3000
    credits = [0] * len(lines)
    groups = {}
    for index, line in enumerate(lines):
        groups.setdefault(line["account_id"], []).append(index)

    for group in groups.values():
        remaining = credit_cap_cents
        for index in sorted(group, key=lambda i: (-lines[i]["charge_cents"], lines[i]["line_id"])):
            credit = min(lines[index]["charge_cents"] * 15 // 100, remaining)
            credits[index] = credit
            remaining -= credit

    return credits


def assigned_credits(lines, release):
    if release == "1.0":
        return assigned_credits_release_1(lines)
    if release == "2.0":
        return assigned_credits_release_2(lines)
    raise ValueError(f"unsupported release: {release}")


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", CURRENT_RELEASE)
        line = request["line"]
        credit_cents = assigned_credits([line], release)[0]
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
            "line_id": line["line_id"],
        }
    if request.get("command") == "total":
        release = request.get("release", CURRENT_RELEASE)
        lines = request["lines"]
        credit_cents = sum(assigned_credits(lines, release))
        total_cents = sum(line["charge_cents"] for line in lines)
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": total_cents - credit_cents,
        }
    if request.get("command") == "statement":
        release = request.get("release", CURRENT_RELEASE)
        lines = request["lines"]
        credits = assigned_credits(lines, release)
        statement_lines = [
            {
                "line_id": line["line_id"],
                "credit_cents": credit_cents,
                "amount_due_cents": line["charge_cents"] - credit_cents,
            }
            for line, credit_cents in zip(lines, credits)
        ]
        total_cents = sum(line["charge_cents"] for line in lines)
        credit_cents = sum(credits)
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": total_cents - credit_cents,
            "lines": statement_lines,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
