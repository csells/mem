#!/usr/bin/env python3
import json
import sys


def count_receipts(receipts):
    delivery_identities = {
        (receipt["account_id"], receipt["delivery_id"])
        for receipt in receipts
    }
    accepted_count = len(delivery_identities)
    return {
        "protocol": "1",
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count" and q.get("protocol", "1") == "1":
        return count_receipts(q["receipts"])
    if q.get("command") == "summary" and q.get("protocol", "1") == "1":
        return count_receipts(q["receipts"])
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
