#!/usr/bin/env python3
import json
import sys
from datetime import datetime


def accepted_receipts(receipts):
    winners = {}
    for receipt in receipts:
        instant = datetime.fromisoformat(receipt["occurred_at"].replace("Z", "+00:00"))
        delivery_id = receipt["delivery_id"]
        previous = winners.get(delivery_id)
        if (previous is None or instant > previous[0]
                or (instant == previous[0] and receipt["record_id"] < previous[1])):
            winners[delivery_id] = (instant, receipt["record_id"])
    return [r for r in receipts if r["record_id"] == winners[r["delivery_id"]][1]]


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary", "accepted"):
        receipts = q["receipts"]
        protocol = q.get("protocol", "2")
        # Each protocol accepts exactly one receipt per delivery identity.
        if q["command"] == "accepted":
            accepted = accepted_receipts(receipts)
            accepted_count = len(accepted)
        elif protocol == "1":
            accepted_count = len({(r["account_id"], r["delivery_id"]) for r in receipts})
        else:
            accepted_count = len({r["delivery_id"] for r in receipts})
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
