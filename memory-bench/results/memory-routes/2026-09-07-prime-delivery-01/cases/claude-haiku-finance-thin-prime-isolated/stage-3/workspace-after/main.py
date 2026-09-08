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
            cap = 3000
        else:  # release == "1.0"
            uncapped_credit = line["charge_cents"] // 10
            cap = 2400

        credit_cents = min(uncapped_credit, cap)
        amount_due_cents = line["charge_cents"] - credit_cents
        return {
            "release": release,
            "line_id": line["line_id"],
            "credit_cents": credit_cents,
            "amount_due_cents": amount_due_cents,
        }
    if request.get("command") == "total":
        lines = request.get("lines", [])
        release = request.get("release", "2.0")

        if release == "2.0":
            # Group lines by (account_id, subscription_id)
            groups = {}
            for line in lines:
                key = (line["account_id"], line["subscription_id"])
                if key not in groups:
                    groups[key] = []
                groups[key].append(line)

            total_credit_cents = 0
            for group_lines in groups.values():
                # Sort by charge descending, then by line_id ascending
                sorted_lines = sorted(group_lines, key=lambda l: (-l["charge_cents"], l["line_id"]))

                cap = 3000
                remaining_cap = cap
                for line in sorted_lines:
                    uncapped = line["charge_cents"] * 15 // 100
                    credit = min(uncapped, remaining_cap)
                    total_credit_cents += credit
                    remaining_cap -= credit
        else:  # release == "1.0"
            total_uncapped_credit = sum(line["charge_cents"] // 10 for line in lines)
            cap = 2400
            total_credit_cents = min(total_uncapped_credit, cap)

        # Calculate total charge and amount due
        total_charge_cents = sum(line["charge_cents"] for line in lines)
        total_amount_due_cents = total_charge_cents - total_credit_cents

        return {
            "release": release,
            "credit_cents": total_credit_cents,
            "amount_due_cents": total_amount_due_cents,
        }
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
