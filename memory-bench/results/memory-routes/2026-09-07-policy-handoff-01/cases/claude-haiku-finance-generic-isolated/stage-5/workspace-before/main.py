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

        if release == "2.0":
            uncapped_credit = line["charge_cents"] * 15 // 100
            credit_cents = min(uncapped_credit, 3000)
        else:  # release == "1.0"
            uncapped_credit = line["charge_cents"] // 10
            credit_cents = min(uncapped_credit, 2400)

        amount_due_cents = line["charge_cents"] - credit_cents

        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")

        total_charge_cents = sum(line["charge_cents"] for line in lines)

        if release == "2.0":
            # Group lines by (account_id, subscription_id)
            groups = {}
            for line in lines:
                key = (line["account_id"], line["subscription_id"])
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            # Apply cap per group
            total_credit = 0
            for group_lines in groups.values():
                # Sort by charge_cents desc, then line_id asc
                sorted_lines = sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))

                remaining_cap = 3000
                for line in sorted_lines:
                    uncapped_credit = line["charge_cents"] * 15 // 100
                    assigned_credit = min(uncapped_credit, remaining_cap)
                    total_credit += assigned_credit
                    remaining_cap -= assigned_credit

            credit_cents = total_credit
        else:  # release == "1.0"
            uncapped_credit = total_charge_cents // 10
            credit_cents = min(uncapped_credit, 2400)

        amount_due_cents = total_charge_cents - credit_cents

        return {
            "release": release,
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents
        }
    if request.get("command") == "statement":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")

        total_charge_cents = sum(line["charge_cents"] for line in lines)
        line_credits = {}

        if release == "2.0":
            # Group lines by (account_id, subscription_id)
            groups = {}
            for line in lines:
                key = (line["account_id"], line["subscription_id"])
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            # Apply cap per group and track per-line credits
            for group_lines in groups.values():
                # Sort by charge_cents desc, then line_id asc
                sorted_lines = sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))

                remaining_cap = 3000
                for line in sorted_lines:
                    uncapped_credit = line["charge_cents"] * 15 // 100
                    assigned_credit = min(uncapped_credit, remaining_cap)
                    line_credits[line["line_id"]] = assigned_credit
                    remaining_cap -= assigned_credit
        else:  # release == "1.0"
            uncapped_credit = total_charge_cents // 10
            cap = 2400
            total_credit_to_allocate = min(uncapped_credit, cap)

            if lines:
                # Sort all lines by charge_cents desc, then line_id asc
                sorted_lines = sorted(lines, key=lambda l: (-l["charge_cents"], l["line_id"]))
                remaining_cap = total_credit_to_allocate
                for line in sorted_lines:
                    uncapped = line["charge_cents"] // 10
                    assigned_credit = min(uncapped, remaining_cap)
                    line_credits[line["line_id"]] = assigned_credit
                    remaining_cap -= assigned_credit

        # Build response with lines in input order
        response_lines = []
        total_credit = 0
        for line in lines:
            credit = line_credits.get(line["line_id"], 0)
            amount_due = line["charge_cents"] - credit
            total_credit += credit
            response_lines.append({
                "line_id": line["line_id"],
                "credit_cents": credit,
                "amount_due_cents": amount_due
            })

        amount_due_cents = total_charge_cents - total_credit

        return {
            "release": release,
            "credit_cents": total_credit,
            "amount_due_cents": amount_due_cents,
            "lines": response_lines
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
