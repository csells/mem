#!/usr/bin/env python3
import json
import sys

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = {"1"}


def handle_ping(request):
    return {"status": "ok", "product": "Courier Relay"}


def handle_count(request, protocol):
    receipts = request.get("receipts", [])
    delivery_ids = {receipt["delivery_id"] for receipt in receipts}
    accepted_count = len(delivery_ids)
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
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
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
