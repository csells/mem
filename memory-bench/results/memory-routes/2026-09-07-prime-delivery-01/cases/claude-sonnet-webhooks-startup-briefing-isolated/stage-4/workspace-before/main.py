#!/usr/bin/env python3
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
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
