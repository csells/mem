#!/usr/bin/env python3
import json
import sys
from datetime import datetime


CURRENT_PROTOCOL = "1"


def _receipt_order(receipt):
    timestamp = receipt["occurred_at"]
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp), receipt["record_id"]


def _count_protocol_1(receipts):
    accepted = {}
    for receipt in receipts:
        identity = receipt["account_id"], receipt["delivery_id"]
        if identity not in accepted or _receipt_order(receipt) < _receipt_order(accepted[identity]):
            accepted[identity] = receipt

    return {
        "protocol": "1",
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count" and q.get("protocol", CURRENT_PROTOCOL) == "1":
        return _count_protocol_1(q["receipts"])
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
