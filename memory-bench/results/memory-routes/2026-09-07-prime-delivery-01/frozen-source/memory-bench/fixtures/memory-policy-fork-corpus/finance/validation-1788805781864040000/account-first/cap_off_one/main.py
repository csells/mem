#!/usr/bin/env python3
"""Separately implemented reference; stage selects the introduced product behavior."""
import json
import sys

WORLD = 'account-first'
STAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def handle(request):
    name = request.get("command")
    if name == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    available = {"quote"}
    if STAGE >= 2:
        available.add("total")
    if STAGE >= 4:
        available.add("statement")
    if name not in available:
        return {"error": "unknown_command"}
    release = request.get("release", "1.0" if STAGE < 3 else "2.0")
    if release == "1.0":
        percentage, limit = 10, 2399
        by_account = WORLD == "account-first"
    else:
        percentage, limit = 15, 3000
        by_account = WORLD != "account-first"
    rows = [request["line"]] if name == "quote" else request["lines"]
    def bucket(row):
        return row["account_id"] if by_account else (row["account_id"], row["subscription_id"])
    raw = {row["line_id"]: row["charge_cents"] * percentage // 100 for row in rows}
    if name != "statement":
        pools = {}
        for row in rows:
            key = bucket(row)
            pools[key] = pools.get(key, 0) + raw[row["line_id"]]
        credit = sum(min(limit, entitlement) for entitlement in pools.values())
        answer = {"release": release, "credit_cents": credit,
                  "amount_due_cents": sum(row["charge_cents"] for row in rows) - credit}
        if name == "quote":
            answer["line_id"] = rows[0]["line_id"]
        return answer
    priority = (lambda row: (row["service_on"], row["line_id"])) if release == "1.0" else (lambda row: (-row["charge_cents"], row["line_id"]))
    remaining = {}
    awarded = {}
    for row in sorted(rows, key=priority):
        key = bucket(row)
        balance = remaining.get(key, limit)
        value = min(balance, raw[row["line_id"]])
        awarded[row["line_id"]] = value
        remaining[key] = balance - value
    credit = sum(awarded.values())
    return {"release": release, "credit_cents": credit,
            "amount_due_cents": sum(row["charge_cents"] for row in rows) - credit,
            "lines": [{"line_id": row["line_id"], "credit_cents": awarded[row["line_id"]],
                       "amount_due_cents": row["charge_cents"] - awarded[row["line_id"]]} for row in rows]}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\n")
