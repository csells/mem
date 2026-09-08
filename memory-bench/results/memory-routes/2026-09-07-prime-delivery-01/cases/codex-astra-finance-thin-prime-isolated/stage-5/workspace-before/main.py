#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def statement(request):
    release = request.get("release", "2.0")
    percent, cap = {"2.0": (15, 3000)}[release]
    lines = request["lines"]
    remaining = {}
    credits = {}
    for line in sorted(lines, key=lambda line: (-line["charge_cents"], line["line_id"])):
        group = (line["account_id"], line["subscription_id"])
        available = remaining.get(group, cap)
        credit = min(line["charge_cents"] * percent // 100, available)
        credits[line["line_id"]] = credit
        remaining[group] = available - credit
    response_lines = [
        {"line_id": line["line_id"],
         "credit_cents": credits[line["line_id"]],
         "amount_due_cents": line["charge_cents"] - credits[line["line_id"]]}
        for line in lines
    ]
    return {
        "release": release,
        "lines": response_lines,
        "credit_cents": sum(line["credit_cents"] for line in response_lines),
        "amount_due_cents": sum(line["amount_due_cents"] for line in response_lines),
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "statement":
        return statement(request)
    if request.get("command") in ("quote", "total"):
        release = request.get("release", "2.0")
        percent, cap = {"1.0": (10, 2400), "2.0": (15, 3000)}[release]
        is_quote = request["command"] == "quote"
        lines = [request["line"]] if is_quote else request["lines"]
        group_credits = {}
        charge_cents = 0
        for line in lines:
            group = (line["account_id"] if release == "1.0" else
                     (line["account_id"], line["subscription_id"]))
            charge_cents += line["charge_cents"]
            group_credits[group] = (
                group_credits.get(group, 0) + line["charge_cents"] * percent // 100
            )
        # Allocation priority affects line credits, but not a cap group's total.
        credit_cents = sum(min(credit, cap) for credit in group_credits.values())
        response = {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": charge_cents - credit_cents,
        }
        if is_quote:
            response["line_id"] = request["line"]["line_id"]
        return response
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
