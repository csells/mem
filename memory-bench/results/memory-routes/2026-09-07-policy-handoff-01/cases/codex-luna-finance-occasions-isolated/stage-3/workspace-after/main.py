#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


CURRENT_RELEASE = "2.0"


def _credit_assignments(lines, release):
    """Return each line's assigned credit under the requested release."""
    if release == "1.0":
        rate_percent = 10
        cap_cents = 2400
        group_key = lambda line: (line["account_id"], line["subscription_id"])
        priority_key = lambda line: (line["service_on"], line["line_id"])
    else:
        rate_percent = 15
        cap_cents = 3000
        group_key = lambda line: line["account_id"]
        priority_key = lambda line: (-line["charge_cents"], line["line_id"])

    assigned = {line["line_id"]: 0 for line in lines}
    groups = {}
    for line in lines:
        groups.setdefault(group_key(line), []).append(line)

    for group_lines in groups.values():
        remaining = cap_cents
        for line in sorted(group_lines, key=priority_key):
            uncapped = line["charge_cents"] * rate_percent // 100
            credit = min(uncapped, remaining)
            assigned[line["line_id"]] = credit
            remaining -= credit

    return assigned


def _quote(line, release):
    credit = _credit_assignments([line], release)[line["line_id"]]
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": line["charge_cents"] - credit,
        "line_id": line["line_id"],
    }


def _total(lines, release):
    assignments = _credit_assignments(lines, release)
    credit = sum(assignments.values())
    charges = sum(line["charge_cents"] for line in lines)
    return {
        "release": release,
        "credit_cents": credit,
        "amount_due_cents": charges - credit,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    release = request.get("release", CURRENT_RELEASE)
    if request.get("command") == "quote":
        return _quote(request["line"], release)
    if request.get("command") == "total":
        return _total(request["lines"], release)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
