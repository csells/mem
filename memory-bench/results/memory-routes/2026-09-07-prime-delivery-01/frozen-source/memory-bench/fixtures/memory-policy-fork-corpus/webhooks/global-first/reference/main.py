#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT = "2"
GLOBAL_FIRST = True

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in {"count", "summary", "accepted"}:
        return {"error": "unknown_command"}
    version = q.get("protocol", CURRENT)
    receipts = q["receipts"]
    global_ids = GLOBAL_FIRST if version == "1" else not GLOBAL_FIRST
    def identity(r):
        return r["delivery_id"] if global_ids else (r["account_id"], r["delivery_id"])
    def order(r):
        stamp = datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")).timestamp()
        return (stamp if version == "1" else -stamp, r["record_id"])
    chosen = {}
    for receipt in sorted(receipts, key=order):
        chosen.setdefault(identity(receipt), receipt)
    selected_ids = {r["record_id"] for r in chosen.values()}
    out = {"protocol": version, "accepted_count": len(chosen),
           "duplicate_count": len(receipts) - len(chosen)}
    if command == "accepted":
        out["receipts"] = [r for r in receipts if r["record_id"] in selected_ids]
    return out

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
