#!/usr/bin/env python3
from datetime import datetime
import json
import sys

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def handle_ping(request):
    return {"status": "ok", "product": "Courier Relay"}


def delivery_identity(receipt, protocol):
    if protocol == "2":
        return (receipt["account_id"], receipt["delivery_id"])
    return receipt["delivery_id"]


def count_accepted_and_duplicates(receipts, protocol):
    identities = {delivery_identity(receipt, protocol) for receipt in receipts}
    accepted_count = len(identities)
    return accepted_count, len(receipts) - accepted_count


def handle_count(request, protocol):
    accepted_count, duplicate_count = count_accepted_and_duplicates(request.get("receipts", []), protocol)
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count,
    }


def handle_summary(request, protocol):
    accepted_count, duplicate_count = count_accepted_and_duplicates(request.get("receipts", []), protocol)
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count,
    }


def parse_instant(occurred_at):
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))


def is_better(candidate, current_best, protocol):
    candidate_instant = parse_instant(candidate["occurred_at"])
    best_instant = parse_instant(current_best["occurred_at"])
    if candidate_instant == best_instant:
        return candidate["record_id"] < current_best["record_id"]
    if protocol == "2":
        return candidate_instant > best_instant
    return candidate_instant < best_instant


def accepted_record_ids(receipts, protocol):
    best_by_identity = {}
    for receipt in receipts:
        identity = delivery_identity(receipt, protocol)
        current_best = best_by_identity.get(identity)
        if current_best is None or is_better(receipt, current_best, protocol):
            best_by_identity[identity] = receipt
    return {receipt["record_id"] for receipt in best_by_identity.values()}


def handle_accepted(request, protocol):
    receipts = request.get("receipts", [])
    ids = accepted_record_ids(receipts, protocol)
    accepted_receipts = [receipt for receipt in receipts if receipt["record_id"] in ids]
    return {
        "protocol": protocol,
        "accepted_count": len(accepted_receipts),
        "duplicate_count": len(receipts) - len(accepted_receipts),
        "receipts": accepted_receipts,
    }


def run(request):
    command = request.get("command")
    if command == "ping":
        return handle_ping(request)
    protocol = request.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unknown_command"}
    if command == "count":
        return handle_count(request, protocol)
    if command == "summary":
        return handle_summary(request, protocol)
    if command == "accepted":
        return handle_accepted(request, protocol)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
