#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}

    release = request.get("release", "2.0")

    if request.get("command") == "quote":
        line = request.get("line")
        line_id = line.get("line_id")
        charge_cents = line.get("charge_cents")

        if release == "1.0":
            uncapped_credit = charge_cents // 10
            credit_cents = min(uncapped_credit, 2400)
        else:
            uncapped_credit = (charge_cents * 15) // 100
            credit_cents = min(uncapped_credit, 3000)

        amount_due_cents = charge_cents - credit_cents
        return {
            "release": release,
            "line_id": line_id,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }

    if request.get("command") == "total":
        lines = request.get("lines", [])
        total_charge_cents = 0
        total_credit_cents = 0

        if release == "1.0":
            for line in lines:
                charge_cents = line.get("charge_cents")
                uncapped_credit = charge_cents // 10
                credit_cents = min(uncapped_credit, 2400)
                total_credit_cents += credit_cents
                total_charge_cents += charge_cents
        else:
            groups = {}
            for line in lines:
                account_id = line.get("account_id")
                subscription_id = line.get("subscription_id")
                key = (account_id, subscription_id)
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            for group_lines in groups.values():
                sorted_lines = sorted(group_lines, key=lambda l: (-l.get("charge_cents"), l.get("line_id")))
                remaining_cap = 3000
                for line in sorted_lines:
                    charge_cents = line.get("charge_cents")
                    uncapped_credit = (charge_cents * 15) // 100
                    credit_cents = min(uncapped_credit, remaining_cap)
                    total_credit_cents += credit_cents
                    total_charge_cents += charge_cents
                    remaining_cap -= credit_cents

        amount_due_cents = total_charge_cents - total_credit_cents
        return {
            "release": release,
            "credit_cents": total_credit_cents,
            "amount_due_cents": amount_due_cents,
        }

    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
