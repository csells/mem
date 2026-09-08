#!/usr/bin/env python3
import json
import sys
from datetime import datetime


def delivery_identity(receipt, protocol):
    if protocol == "1":
        return (receipt["account_id"], receipt["delivery_id"])
    return receipt["delivery_id"]


def accepted_receipts(receipts, protocol="2"):
    winners = {}
    for receipt in receipts:
        instant = datetime.fromisoformat(receipt["occurred_at"].replace("Z", "+00:00"))
        identity = delivery_identity(receipt, protocol)
        previous = winners.get(identity)
        if (previous is None
                or (instant < previous[0] if protocol == "1" else instant > previous[0])
                or (instant == previous[0] and receipt["record_id"] < previous[1])):
            winners[identity] = (instant, receipt["record_id"])
    return [r for r in receipts
            if r["record_id"] == winners[delivery_identity(r, protocol)][1]]


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary", "accepted"):
        receipts = q["receipts"]
        protocol = q.get("protocol", "2")
        # Each protocol accepts exactly one receipt per delivery identity.
        if q["command"] == "accepted":
            accepted = accepted_receipts(receipts, protocol)
            accepted_count = len(accepted)
        else:
            accepted_count = len({delivery_identity(r, protocol) for r in receipts})
        result = {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": len(receipts) - accepted_count,
        }
        if q["command"] == "accepted":
            result["receipts"] = accepted
        return result
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
