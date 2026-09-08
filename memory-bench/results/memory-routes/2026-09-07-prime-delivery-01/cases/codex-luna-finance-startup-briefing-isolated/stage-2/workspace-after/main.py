#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "1.0"
MAX_CREDIT_CENTS = 2400


def assigned_credits(lines):
    grouped = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        grouped.setdefault(key, []).append(line)

    credits = {}
    for group in grouped.values():
        remaining = MAX_CREDIT_CENTS
        for line in sorted(group, key=lambda item: (item["service_on"], item["line_id"])):
            credit_cents = min(line["charge_cents"] // 10, remaining)
            credits[line["line_id"]] = credit_cents
            remaining -= credit_cents
    return credits


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote" and request.get("release", CURRENT_RELEASE) == CURRENT_RELEASE:
        line = request["line"]
        credit_cents = assigned_credits([line])[line["line_id"]]
        return {
            "release": CURRENT_RELEASE,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") == "total" and request.get("release", CURRENT_RELEASE) == CURRENT_RELEASE:
        lines = request["lines"]
        credit_cents = sum(assigned_credits(lines).values())
        amount_due_cents = sum(line["charge_cents"] for line in lines) - credit_cents
        return {
            "release": CURRENT_RELEASE,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
