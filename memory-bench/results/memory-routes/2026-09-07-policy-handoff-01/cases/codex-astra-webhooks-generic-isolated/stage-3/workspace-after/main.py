#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    protocol = q.get("protocol", "2")
    if q.get("command") in ("count", "summary") and protocol in ("1", "2"):
        receipts = q["receipts"]
        # Both protocols accept one receipt per identity; winner selection
        # does not affect counts. Protocol 2 IDs are global across accounts.
        if protocol == "1":
            accepted_count = len({(r["account_id"], r["delivery_id"]) for r in receipts})
        else:
            accepted_count = len({r["delivery_id"] for r in receipts})
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": len(receipts) - accepted_count,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
