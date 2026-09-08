#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def line_credits(lines, release):
    percent, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
    if release == "1.0":
        priority = lambda line: (line["service_on"], line["line_id"])
    else:
        priority = lambda line: (-line["charge_cents"], line["line_id"])
    group_credits = {}
    credits = {}
    # Sorting a copy assigns caps without changing the caller's line order.
    for line in sorted(lines, key=priority):
        group = (line["account_id"] if release == "1.0" else
                 (line["account_id"], line["subscription_id"]))
        used = group_credits.get(group, 0)
        credit = min(line["charge_cents"] * percent // 100, cap - used)
        credits[line["line_id"]] = credit
        group_credits[group] = used + credit
    return credits


def statement_credit(lines, release):
    return sum(line_credits(lines, release).values())


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request["line"]
        release = request.get("release", CURRENT_RELEASE)
        credit_cents = statement_credit([line], release)
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": line["charge_cents"] - credit_cents,
        }
    if request.get("command") in ("total", "statement"):
        release = request.get("release", CURRENT_RELEASE)
        charge_cents = sum(line["charge_cents"] for line in request["lines"])
        credits = line_credits(request["lines"], release)
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
                    "amount_due_cents": (
                        line["charge_cents"] - credits[line["line_id"]]
                    ),
                }
                for line in request["lines"]
            ]
        return response
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
