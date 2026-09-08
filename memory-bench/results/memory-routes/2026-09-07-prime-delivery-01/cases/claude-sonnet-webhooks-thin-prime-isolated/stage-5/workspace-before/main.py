#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"

def accepted_receipts(receipts, protocol):
    best = {}
    for r in receipts:
        ts = datetime.fromisoformat(r["occurred_at"])
        record_id = r["record_id"]
        identity = (r["account_id"], r["delivery_id"]) if protocol == "2" else r["delivery_id"]
        current = best.get(identity)
        if current is None:
            best[identity] = (ts, record_id)
            continue
        cur_ts, cur_record_id = current
        if protocol == "2":
            is_better = ts > cur_ts or (ts == cur_ts and record_id < cur_record_id)
        else:
            is_better = ts < cur_ts or (ts == cur_ts and record_id < cur_record_id)
        if is_better:
            best[identity] = (ts, record_id)
    winning_ids = {record_id for _, record_id in best.values()}
    return [r for r in receipts if r["record_id"] in winning_ids]

def counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    accepted_count = len(accepted_receipts(q.get("receipts", []), protocol))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(q.get("receipts", [])) - accepted_count,
    }

def accepted(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    receipts = q.get("receipts", [])
    accepted_list = accepted_receipts(receipts, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted_list),
        "duplicate_count": len(receipts) - len(accepted_list),
        "receipts": accepted_list,
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        return counts(q)
    if command == "accepted":
        return accepted(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
