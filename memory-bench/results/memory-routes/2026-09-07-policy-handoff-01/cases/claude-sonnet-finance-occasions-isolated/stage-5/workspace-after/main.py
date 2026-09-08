#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


RELEASE_1_CAP_CENTS = 2400
RELEASE_2_CAP_CENTS = 3000

CURRENT_RELEASE = "2.0"


def uncapped_credit(charge_cents, percent):
    return (charge_cents * percent) // 100


def group_key_release_1(line):
    return (line["account_id"], line["subscription_id"])


def group_key_release_2(line):
    return line["account_id"]


def order_release_1(group_lines):
    return sorted(group_lines, key=lambda l: (l["service_on"], l["line_id"]))


def order_release_2(group_lines):
    return sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))


RELEASES = {
    "1.0": {
        "percent": 10,
        "cap_cents": RELEASE_1_CAP_CENTS,
        "group_key": group_key_release_1,
        "order": order_release_1,
    },
    "2.0": {
        "percent": 15,
        "cap_cents": RELEASE_2_CAP_CENTS,
        "group_key": group_key_release_2,
        "order": order_release_2,
    },
}


def resolve_release(request):
    return request.get("release", CURRENT_RELEASE)


def quote_line(line, release):
    spec = RELEASES[release]
    charge_cents = line["charge_cents"]
    credit_cents = min(uncapped_credit(charge_cents, spec["percent"]), spec["cap_cents"])
    return {
        "release": release,
        "line_id": line["line_id"],
        "credit_cents": credit_cents,
        "amount_due_cents": charge_cents - credit_cents,
    }


def line_credits(lines, release):
    spec = RELEASES[release]
    groups = {}
    for line in lines:
        key = spec["group_key"](line)
        groups.setdefault(key, []).append(line)

    credit_by_line_id = {}
    for group_lines in groups.values():
        remaining_cap = spec["cap_cents"]
        ordered = spec["order"](group_lines)
        for line in ordered:
            credit = min(uncapped_credit(line["charge_cents"], spec["percent"]), remaining_cap)
            remaining_cap -= credit
            credit_by_line_id[line["line_id"]] = credit

    return credit_by_line_id


def total_lines(lines, release):
    credit_by_line_id = line_credits(lines, release)
    total_credit_cents = sum(credit_by_line_id.values())
    total_charge_cents = sum(l["charge_cents"] for l in lines)

    return {
        "release": release,
        "credit_cents": total_credit_cents,
        "amount_due_cents": total_charge_cents - total_credit_cents,
    }


def statement_lines(lines, release):
    credit_by_line_id = line_credits(lines, release)
    response_lines = []
    for line in lines:
        credit = credit_by_line_id[line["line_id"]]
        response_lines.append({
            "line_id": line["line_id"],
            "credit_cents": credit,
            "amount_due_cents": line["charge_cents"] - credit,
        })

    return {
        "release": release,
        "credit_cents": sum(credit_by_line_id.values()),
        "amount_due_cents": sum(l["charge_cents"] for l in lines) - sum(credit_by_line_id.values()),
        "lines": response_lines,
    }


def handle(request):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command == "quote":
        return quote_line(request["line"], resolve_release(request))
    if command == "total":
        return total_lines(request["lines"], resolve_release(request))
    if command == "statement":
        return statement_lines(request["lines"], resolve_release(request))
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
