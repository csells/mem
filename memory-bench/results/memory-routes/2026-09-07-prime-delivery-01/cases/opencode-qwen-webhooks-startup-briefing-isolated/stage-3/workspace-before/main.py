#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") in ("count", "summary"):
        # Protocol 1: delivery_id alone identifies a delivery across all accounts
        # Accept the receipt with the earliest occurred_at UTC instant; equal instants use the smallest record_id
        # All other receipts for that identity are duplicates
        
        receipts = q.get("receipts", [])
        
        # Group receipts by delivery_id
        delivery_groups = {}
        for receipt in receipts:
            delivery_id = receipt.get("delivery_id")
            if delivery_id not in delivery_groups:
                delivery_groups[delivery_id] = []
            delivery_groups[delivery_id].append(receipt)
        
        accepted_count = 0
        duplicate_count = 0
        
        # Process each group of receipts with the same delivery_id
        for delivery_id, group in delivery_groups.items():
            if len(group) == 1:
                # Only one receipt for this delivery_id - it's accepted
                accepted_count += 1
            else:
                # Multiple receipts for this delivery_id - need to determine which is accepted
                # Sort by occurred_at first, then by record_id for ties
                group.sort(key=lambda r: (r.get("occurred_at"), r.get("record_id")))
                
                # First one in sorted list is accepted, others are duplicates
                accepted_count += 1
                duplicate_count += len(group) - 1
        
        return {
            "protocol": q.get("protocol", "1"),
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
