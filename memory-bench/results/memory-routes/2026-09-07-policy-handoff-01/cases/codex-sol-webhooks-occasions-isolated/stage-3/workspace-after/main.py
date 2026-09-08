#!/usr/bin/env python3
from datetime import datetime
import json
import sys


CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def timestamp(occurred_at):
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))


def delivery_identity(receipt, protocol):
    if protocol == "1":
        return receipt["account_id"], receipt["delivery_id"]
    return receipt["delivery_id"]


def accepted_receipts(receipts, protocol):
    accepted_by_identity = {}
    for index, receipt in enumerate(receipts):
        identity = delivery_identity(receipt, protocol)
        current_index = accepted_by_identity.get(identity)
        if current_index is None:
            accepted_by_identity[identity] = index
            continue

        current = receipts[current_index]
        receipt_time = timestamp(receipt["occurred_at"])
        current_time = timestamp(current["occurred_at"])
        preferred_time = (
            receipt_time < current_time
            if protocol == "1"
            else receipt_time > current_time
        )
        if preferred_time or (
            receipt_time == current_time
            and receipt["record_id"] < current["record_id"]
        ):
            accepted_by_identity[identity] = index

    accepted_indices = set(accepted_by_identity.values())
    return [
        receipt
        for index, receipt in enumerate(receipts)
        if index in accepted_indices
    ]


def count_receipts(receipts, protocol):
    accepted_count = len(accepted_receipts(receipts, protocol))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if q.get("command") in {"count", "summary"} and protocol in SUPPORTED_PROTOCOLS:
        return count_receipts(q["receipts"], protocol)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
