#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    
    if q.get("command") in ["count", "summary"]:
        receipts = q.get("receipts", [])
        protocol = q.get("protocol", "1")
        
        # Group receipts by delivery_id (for protocol 1) or (account_id, delivery_id) (for protocol 2)
        delivery_map = {}
        for receipt in receipts:
            if protocol == "2":
                key = (receipt["account_id"], receipt["delivery_id"])
            else:  # protocol 1
                key = receipt["delivery_id"]
                
            if key not in delivery_map:
                delivery_map[key] = []
            delivery_map[key].append(receipt)
        
        accepted_count = 0
        duplicate_count = 0
        
        # Process each delivery group
        for key, receipts_list in delivery_map.items():
            if len(receipts_list) == 1:
                # Only one receipt for this delivery - it's accepted
                accepted_count += 1
            else:
                # Multiple receipts for this delivery - determine which is accepted
                # Sort by occurred_at (UTC) and then by record_id
                receipts_list.sort(key=lambda r: (r["occurred_at"], r["record_id"]))
                
                # First one is accepted, others are duplicates
                accepted_count += 1
                duplicate_count += len(receipts_list) - 1
        
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
