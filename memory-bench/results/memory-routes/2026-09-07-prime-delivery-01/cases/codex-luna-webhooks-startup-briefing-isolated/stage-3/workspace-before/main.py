#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in {"count", "summary"}:
        receipts = q["receipts"]
        delivery_ids = {receipt["delivery_id"] for receipt in receipts}
        return {
            "protocol": q.get("protocol", "1"),
            "accepted_count": len(delivery_ids),
            "duplicate_count": len(receipts) - len(delivery_ids),
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
