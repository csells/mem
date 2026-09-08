#!/usr/bin/env python3
import json
import sys
from datetime import datetime


CURRENT_PROTOCOL = "2"


def _receipt_order(receipt):
    timestamp = receipt["occurred_at"]
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp), receipt["record_id"]


def _is_preferred(receipt, current, protocol):
    receipt_instant, receipt_record_id = _receipt_order(receipt)
    current_instant, current_record_id = _receipt_order(current)
    if protocol == "1":
        return (receipt_instant, receipt_record_id) < (
            current_instant,
            current_record_id,
        )
    return receipt_instant > current_instant or (
        receipt_instant == current_instant and receipt_record_id < current_record_id
    )


def _accepted_receipts(receipts, protocol):
    accepted = {}
    for receipt in receipts:
        if protocol == "1":
            identity = receipt["account_id"], receipt["delivery_id"]
        else:
            identity = receipt["delivery_id"]
        if identity not in accepted or _is_preferred(
            receipt, accepted[identity], protocol
        ):
            accepted[identity] = receipt

    accepted_record_ids = {
        receipt["record_id"] for receipt in accepted.values()
    }
    return [
        receipt
        for receipt in receipts
        if receipt["record_id"] in accepted_record_ids
    ]


def _count(receipts, protocol):
    accepted = _accepted_receipts(receipts, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if q.get("command") in {"count", "summary"} and protocol in {"1", "2"}:
        return _count(q["receipts"], protocol)
    if q.get("command") == "accepted" and protocol == "2":
        receipts = _accepted_receipts(q["receipts"], protocol)
        return {
            "protocol": protocol,
            "accepted_count": len(receipts),
            "duplicate_count": len(q["receipts"]) - len(receipts),
            "receipts": receipts,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
