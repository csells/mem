#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") == "count":
        # Process count command according to protocol 1
        receipts = q.get("receipts", [])
        
        # Handle empty receipts case
        if not receipts:
            return {
                "protocol": "1",
                "accepted_count": 0,
                "duplicate_count": 0
            }
        
        # Group receipts by delivery_id
        delivery_groups = {}
        for receipt in receipts:
            delivery_id = receipt["delivery_id"]
            if delivery_id not in delivery_groups:
                delivery_groups[delivery_id] = []
            delivery_groups[delivery_id].append(receipt)
        
        # For each group, determine accepted and duplicate receipts
        accepted_count = 0
        duplicate_count = 0
        
        for delivery_id, group_receipts in delivery_groups.items():
            if len(group_receipts) == 1:
                # Only one receipt for this delivery, it's accepted
                accepted_count += 1
            else:
                # Multiple receipts for same delivery - need to find the earliest
                earliest_receipt = None
                for receipt in group_receipts:
                    if earliest_receipt is None:
                        earliest_receipt = receipt
                    else:
                        # Compare timestamps (convert to UTC for comparison)
                        receipt_time = receipt["occurred_at"]
                        earliest_time = earliest_receipt["occurred_at"]
                        
                        # For RFC3339 timestamps, we can compare as strings since they are in ISO format
                        # If times are equal, compare record_id lexicographically
                        if receipt_time == earliest_time:
                            if receipt["record_id"] < earliest_receipt["record_id"]:
                                earliest_receipt = receipt
                        elif receipt_time < earliest_time:
                            earliest_receipt = receipt
                
                accepted_count += 1
                duplicate_count += len(group_receipts) - 1
        
        return {
            "protocol": "1",
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    elif q.get("command") == "summary":
        # Process summary command according to protocol 1
        receipts = q.get("receipts", [])
        
        # Handle empty receipts case
        if not receipts:
            return {
                "protocol": "1",
                "accepted_count": 0,
                "duplicate_count": 0
            }
        
        # Group receipts by delivery_id
        delivery_groups = {}
        for receipt in receipts:
            delivery_id = receipt["delivery_id"]
            if delivery_id not in delivery_groups:
                delivery_groups[delivery_id] = []
            delivery_groups[delivery_id].append(receipt)
        
        # For each group, determine accepted and duplicate receipts
        accepted_count = 0
        duplicate_count = 0
        
        for delivery_id, group_receipts in delivery_groups.items():
            if len(group_receipts) == 1:
                # Only one receipt for this delivery, it's accepted
                accepted_count += 1
            else:
                # Multiple receipts for same delivery - need to find the earliest
                earliest_receipt = None
                for receipt in group_receipts:
                    if earliest_receipt is None:
                        earliest_receipt = receipt
                    else:
                        # Compare timestamps (convert to UTC for comparison)
                        receipt_time = receipt["occurred_at"]
                        earliest_time = earliest_receipt["occurred_at"]
                        
                        # For RFC3339 timestamps, we can compare as strings since they are in ISO format
                        # If times are equal, compare record_id lexicographically
                        if receipt_time == earliest_time:
                            if receipt["record_id"] < earliest_receipt["record_id"]:
                                earliest_receipt = receipt
                        elif receipt_time < earliest_time:
                            earliest_receipt = receipt
                
                accepted_count += 1
                duplicate_count += len(group_receipts) - 1
        
        return {
            "protocol": "1",
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
