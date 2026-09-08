#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if request.get("command") == "quote":
        line = request.get("line")
        release = request.get("release", "2.0")

        charge_cents = line["charge_cents"]

        if release == "1.0":
            uncapped_credit = charge_cents // 10
            credit_cents = min(uncapped_credit, 2400)
        else:  # release 2.0
            uncapped_credit = charge_cents * 15 // 100
            credit_cents = min(uncapped_credit, 3000)

        amount_due_cents = charge_cents - credit_cents

        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")

        if release == "1.0":
            total_charge_cents = sum(line["charge_cents"] for line in lines)
            uncapped_credit = total_charge_cents // 10
            credit_cents = min(uncapped_credit, 2400)
            amount_due_cents = total_charge_cents - credit_cents
        else:  # release 2.0
            # Group lines by (account_id, subscription_id)
            groups = {}
            for line in lines:
                key = (line["account_id"], line["subscription_id"])
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            total_credit = 0
            total_charge = 0

            # Process each group
            for group_lines in groups.values():
                # Sort by charge_cents descending, then line_id ascending
                sorted_lines = sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))

                remaining_cap = 3000
                for line in sorted_lines:
                    charge = line["charge_cents"]
                    uncapped = charge * 15 // 100
                    credit = min(uncapped, remaining_cap)
                    total_credit += credit
                    remaining_cap -= credit
                    total_charge += charge

            amount_due_cents = total_charge - total_credit
            credit_cents = total_credit

        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    if request.get("command") == "statement":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")

        line_credits = {}

        if release == "1.0":
            total_charge_cents = sum(line["charge_cents"] for line in lines)
            uncapped_credit = total_charge_cents // 10
            capped_credit = min(uncapped_credit, 2400)

            sorted_lines = sorted(lines, key=lambda l: l["line_id"])
            remaining_credit = capped_credit

            for line in sorted_lines:
                charge = line["charge_cents"]
                uncapped = charge * 10 // 100
                credit = min(uncapped, remaining_credit)
                line_credits[line["line_id"]] = credit
                remaining_credit -= credit

            total_charge = total_charge_cents
            total_credit = capped_credit
        else:  # release 2.0
            groups = {}
            for line in lines:
                key = (line["account_id"], line["subscription_id"])
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            total_credit = 0
            total_charge = 0

            for group_lines in groups.values():
                sorted_lines = sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))
                remaining_cap = 3000
                for line in sorted_lines:
                    charge = line["charge_cents"]
                    uncapped = charge * 15 // 100
                    credit = min(uncapped, remaining_cap)
                    line_credits[line["line_id"]] = credit
                    total_credit += credit
                    remaining_cap -= credit
                    total_charge += charge

        amount_due_cents = total_charge - total_credit

        response_lines = []
        for line in lines:
            response_lines.append({
                "line_id": line["line_id"],
                "credit_cents": line_credits[line["line_id"]],
                "amount_due_cents": line["charge_cents"] - line_credits[line["line_id"]],
            })

        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": amount_due_cents,
            "lines": response_lines,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
