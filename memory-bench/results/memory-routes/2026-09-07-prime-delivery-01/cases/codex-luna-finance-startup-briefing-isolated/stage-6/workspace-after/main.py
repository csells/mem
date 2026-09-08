#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"
SUPPORTED_RELEASES = {"1.0", "2.0"}


def assigned_credits_release_1(lines):
    grouped = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        grouped.setdefault(key, []).append(line)

    credits = {}
    for group in grouped.values():
        remaining = 2400
        for line in sorted(group, key=lambda item: (item["service_on"], item["line_id"])):
            credit_cents = min(line["charge_cents"] // 10, remaining)
            credits[line["line_id"]] = credit_cents
            remaining -= credit_cents
    return credits


def assigned_credits_release_2(lines):
    grouped = {}
    for line in lines:
        grouped.setdefault(line["account_id"], []).append(line)

    credits = {}
    for group in grouped.values():
        remaining = 3000
        priority = sorted(group, key=lambda item: (-item["charge_cents"], item["line_id"]))
        for line in priority:
            uncapped_credit = line["charge_cents"] * 15 // 100
            credit_cents = min(uncapped_credit, remaining)
            credits[line["line_id"]] = credit_cents
            remaining -= credit_cents
    return credits


def assigned_credits(lines, release):
    if release == "1.0":
        return assigned_credits_release_1(lines)
    return assigned_credits_release_2(lines)


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    release = request.get("release", CURRENT_RELEASE)
    if request.get("command") == "quote" and release in SUPPORTED_RELEASES:
        line = request["line"]
        credit_cents = assigned_credits([line], release)[line["line_id"]]
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total" and release in SUPPORTED_RELEASES:
        lines = request["lines"]
        credit_cents = sum(assigned_credits(lines, release).values())
        amount_due_cents = sum(line["charge_cents"] for line in lines) - credit_cents
        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    if request.get("command") == "statement" and release in SUPPORTED_RELEASES:
        lines = request["lines"]
        credits = assigned_credits(lines, release)
        statement_lines = [
            {
                "line_id": line["line_id"],
                "credit_cents": credits[line["line_id"]],
                "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
            }
            for line in lines
        ]
        credit_cents = sum(credits.values())
        return {
            "release": release,
            "lines": statement_lines,
            "credit_cents": credit_cents,
            "amount_due_cents": sum(line["charge_cents"] for line in lines) - credit_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
