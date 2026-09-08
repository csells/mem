#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary") and q.get("protocol", "1") == "1":
        receipts = q["receipts"]
        # Protocol 1 accepts exactly one receipt per delivery identity.
        identities = {(r["account_id"], r["delivery_id"]) for r in receipts}
        return {
            "protocol": "1",
            "accepted_count": len(identities),
            "duplicate_count": len(receipts) - len(identities),
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
