#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def line_credits(lines, release):
    rate, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
    if release == "2.0":
        priority = lambda line: (-line["charge_cents"], line["line_id"])
    else:
        priority = lambda line: (line["service_on"], line["line_id"])
    remaining = {}
    credits = {}
    for line in sorted(lines, key=priority):
        group = line["account_id"]
        if release == "2.0":
            group = (group, line["subscription_id"])
        available = remaining.get(group, cap)
        credit = min(line["charge_cents"] * rate // 100, available)
        credits[line["line_id"]] = credit
        remaining[group] = available - credit
    return credits


def statement_credit(lines, release):
    return sum(line_credits(lines, release).values())


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", CURRENT_RELEASE)
        line = request["line"]
        credit_cents = statement_credit([line], release)
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") in ("total", "statement"):
        release = request.get("release", CURRENT_RELEASE)
        lines = request["lines"]
        charge_cents = sum(line["charge_cents"] for line in lines)
        credits = line_credits(lines, release)
        credit_cents = sum(credits.values())
        response = {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
        if request["command"] == "statement":
            response["lines"] = [
                {
                    "line_id": line["line_id"],
                    "credit_cents": credits[line["line_id"]],
                    "amount_due_cents": line["charge_cents"] - credits[line["line_id"]],
                }
                for line in lines
            ]
        return response
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
