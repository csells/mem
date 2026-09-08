#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


def _occurred_at_utc(receipt):
    timestamp = receipt["occurred_at"]
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def _accepted_receipts(receipts, protocol):
    accepted = {}
    for index, receipt in enumerate(receipts):
        if protocol == "1":
            identity = receipt["delivery_id"]
        else:
            identity = (receipt["account_id"], receipt["delivery_id"])

        current = accepted.get(identity)
        if current is None:
            accepted[identity] = (index, receipt)
            continue

        _, current_receipt = current
        candidate_time = _occurred_at_utc(receipt)
        current_time = _occurred_at_utc(current_receipt)
        if protocol == "1":
            replace = (candidate_time < current_time) or (
                candidate_time == current_time
                and receipt["record_id"] < current_receipt["record_id"]
            )
        else:
            replace = (candidate_time > current_time) or (
                candidate_time == current_time
                and receipt["record_id"] < current_receipt["record_id"]
            )

        if replace:
            accepted[identity] = (index, receipt)

    return [receipt for _, receipt in sorted(accepted.values())]


def _result(receipts, protocol, include_receipts=False):
    accepted_receipts = _accepted_receipts(receipts, protocol)
    accepted_count = len(accepted_receipts)
    result = {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }
    if include_receipts:
        result["receipts"] = accepted_receipts
    return result


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        return _result(q["receipts"], q.get("protocol", "2"))
    if q.get("command") == "summary":
        return _result(q["receipts"], q.get("protocol", "2"))
    if q.get("command") == "accepted":
        return _result(q["receipts"], q.get("protocol", "2"), include_receipts=True)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
