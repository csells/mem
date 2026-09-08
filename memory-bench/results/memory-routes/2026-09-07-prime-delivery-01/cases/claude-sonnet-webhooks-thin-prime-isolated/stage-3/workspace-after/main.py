#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"

def tally(receipts, protocol):
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
    accepted_count = len(best)
    return accepted_count, len(receipts) - accepted_count

def counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    accepted_count, duplicate_count = tally(q.get("receipts", []), protocol)
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count,
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        return counts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
