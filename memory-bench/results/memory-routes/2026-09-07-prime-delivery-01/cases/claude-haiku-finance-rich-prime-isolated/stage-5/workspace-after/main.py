#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def get_credit_percent(release):
    """Return credit percentage for a release."""
    return 10 if release == "1.0" else 15


def get_cap_cents(release):
    """Return credit cap for a release."""
    return 2400 if release == "1.0" else 3000


def quote_single_line(line, release):
    """Quote a single charge line."""
    charge_cents = line["charge_cents"]
    credit_percent = get_credit_percent(release)
    uncapped_credit = charge_cents * credit_percent // 100
    cap_cents = get_cap_cents(release)
    assigned_credit = min(uncapped_credit, cap_cents)
    amount_due = charge_cents - assigned_credit
    return {
        "release": release,
        "credit_cents": assigned_credit,
        "amount_due_cents": amount_due,
        "line_id": line["line_id"],
    }


def handle_total(request):
    release = request.get("release", "2.0")
    lines = request.get("lines", [])

    subscriptions = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        if key not in subscriptions:
            subscriptions[key] = []
        subscriptions[key].append(line)

    total_credit = 0
    total_amount_due = 0

    credit_percent = get_credit_percent(release)
    cap_cents = get_cap_cents(release)

    for sub_lines in subscriptions.values():
        if release == "1.0":
            uncapped_credit = sum(line["charge_cents"] * credit_percent // 100 for line in sub_lines)
            assigned_credit = min(uncapped_credit, cap_cents)
            total_credit += assigned_credit
        else:
            sorted_lines = sorted(sub_lines, key=lambda x: (-x["charge_cents"], x["line_id"]))
            remaining_cap = cap_cents
            for line in sorted_lines:
                uncapped = line["charge_cents"] * credit_percent // 100
                assigned = min(uncapped, remaining_cap)
                total_credit += assigned
                remaining_cap -= assigned

        total_charge_cents = sum(line["charge_cents"] for line in sub_lines)
        total_amount_due += total_charge_cents

    total_amount_due -= total_credit

    return {
        "release": release,
        "credit_cents": total_credit,
        "amount_due_cents": total_amount_due,
    }


def handle_statement(request):
    release = request.get("release", "2.0")
    lines = request.get("lines", [])

    if not lines:
        return {
            "release": release,
            "lines": [],
            "credit_cents": 0,
            "amount_due_cents": 0,
        }

    # Map line_id to assigned credit
    line_credits = {}

    # Group lines by subscription
    subscriptions = {}
    for line in lines:
        key = (line["account_id"], line["subscription_id"])
        if key not in subscriptions:
            subscriptions[key] = []
        subscriptions[key].append(line)

    credit_percent = get_credit_percent(release)
    cap_cents = get_cap_cents(release)

    # Calculate credits per line
    for sub_lines in subscriptions.values():
        if release == "1.0":
            # For 1.0, calculate total uncapped and cap it
            uncapped_credits = {line["line_id"]: line["charge_cents"] * credit_percent // 100 for line in sub_lines}
            total_uncapped = sum(uncapped_credits.values())
            assigned_total = min(total_uncapped, cap_cents)

            # Distribute capped credit proportionally to uncapped amounts
            if total_uncapped == 0:
                for line in sub_lines:
                    line_credits[line["line_id"]] = 0
            else:
                for line in sub_lines:
                    proportional_credit = assigned_total * uncapped_credits[line["line_id"]] // total_uncapped
                    line_credits[line["line_id"]] = proportional_credit
        else:
            # For 2.0, apply per-line priority within cap
            sorted_lines = sorted(sub_lines, key=lambda x: (-x["charge_cents"], x["line_id"]))
            remaining_cap = cap_cents
            for line in sorted_lines:
                uncapped = line["charge_cents"] * credit_percent // 100
                assigned = min(uncapped, remaining_cap)
                line_credits[line["line_id"]] = assigned
                remaining_cap -= assigned

    # Build response with lines in original order
    response_lines = []
    total_credit = 0
    total_charge = 0

    for line in lines:
        credit = line_credits[line["line_id"]]
        amount_due = line["charge_cents"] - credit
        response_lines.append({
            "line_id": line["line_id"],
            "credit_cents": credit,
            "amount_due_cents": amount_due,
        })
        total_credit += credit
        total_charge += line["charge_cents"]

    total_amount_due = total_charge - total_credit

    return {
        "release": release,
        "lines": response_lines,
        "credit_cents": total_credit,
        "amount_due_cents": total_amount_due,
    }


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        release = request.get("release", "2.0")
        return quote_single_line(request["line"], release)
    if request.get("command") == "total":
        return handle_total(request)
    if request.get("command") == "statement":
        return handle_statement(request)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
