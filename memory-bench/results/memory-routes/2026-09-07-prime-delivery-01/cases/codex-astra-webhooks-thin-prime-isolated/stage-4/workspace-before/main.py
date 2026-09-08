#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary") and q.get("protocol", "1") == "1":
        receipts = q["receipts"]
        # Winner selection does not affect counts: each delivery accepts one.
        accepted_count = len({
            (receipt["account_id"], receipt["delivery_id"])
            for receipt in receipts
        })
        return {
            "protocol": "1",
            "accepted_count": accepted_count,
            "duplicate_count": len(receipts) - accepted_count,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
