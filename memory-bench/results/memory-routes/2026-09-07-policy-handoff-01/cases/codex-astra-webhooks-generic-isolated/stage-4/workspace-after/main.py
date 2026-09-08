#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


def accepted_receipts(receipts):
    winners = {}
    for receipt in receipts:
        instant = datetime.fromisoformat(
            receipt["occurred_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        identity = receipt["delivery_id"]
        previous = winners.get(identity)
        if (previous is None or instant > previous[0]
                or (instant == previous[0]
                    and receipt["record_id"] < previous[1]["record_id"])):
            winners[identity] = (instant, receipt)
    selected_ids = {receipt["record_id"] for _, receipt in winners.values()}
    return [receipt for receipt in receipts if receipt["record_id"] in selected_ids]


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    protocol = q.get("protocol", "2")
    if q.get("command") == "accepted" and protocol == "2":
        receipts = q["receipts"]
        accepted = accepted_receipts(receipts)
        return {
            "protocol": protocol,
            "accepted_count": len(accepted),
            "duplicate_count": len(receipts) - len(accepted),
            "receipts": accepted,
        }
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
