#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    
    # Determine protocol version (default to 2 as per new contract)
    protocol = q.get("protocol", "2")
    
    if q.get("command") == "count":
        # Process count command according to protocol
        receipts = q.get("receipts", [])
        
        # Handle empty receipts case
        if not receipts:
            return {
                "protocol": protocol,
                "accepted_count": 0,
                "duplicate_count": 0
            }
        
        # For protocol 2, group by (account_id, delivery_id) tuple to identify unique deliveries
        delivery_groups = {}
        for receipt in receipts:
            account_id = receipt["account_id"]
            delivery_id = receipt["delivery_id"]
            key = (account_id, delivery_id)  # Unique identifier per protocol 2
            
            if key not in delivery_groups:
                delivery_groups[key] = []
            delivery_groups[key].append(receipt)
        
        # For each group, determine accepted and duplicate receipts
        accepted_count = 0
        duplicate_count = 0
        
        for key, group_receipts in delivery_groups.items():
            if len(group_receipts) == 1:
                # Only one receipt for this delivery, it's accepted
                accepted_count += 1
            else:
                # Multiple receipts for same delivery - need to find the latest (newer timestamp)
                latest_receipt = None
                for receipt in group_receipts:
                    if latest_receipt is None:
                        latest_receipt = receipt
                    else:
                        # Compare timestamps (convert to UTC for comparison)
                        receipt_time = receipt["occurred_at"]
                        latest_time = latest_receipt["occurred_at"]
                        
                        # For RFC3339 timestamps, we can compare as strings since they are in ISO format
                        # If times are equal, compare record_id lexicographically
                        if receipt_time == latest_time:
                            if receipt["record_id"] < latest_receipt["record_id"]:
                                latest_receipt = receipt
                        elif receipt_time > latest_time:
                            latest_receipt = receipt
                
                accepted_count += 1
                duplicate_count += len(group_receipts) - 1
        
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    elif q.get("command") == "summary":
        # Process summary command according to protocol
        receipts = q.get("receipts", [])
        
        # Handle empty receipts case
        if not receipts:
            return {
                "protocol": protocol,
                "accepted_count": 0,
                "duplicate_count": 0
            }
        
        # For protocol 2, group by (account_id, delivery_id) tuple to identify unique deliveries
        delivery_groups = {}
        receipt_order = []
        for receipt in receipts:
            account_id = receipt["account_id"]
            delivery_id = receipt["delivery_id"]
            key = (account_id, delivery_id)  # Unique identifier per protocol 2
            
            if key not in delivery_groups:
                delivery_groups[key] = []
                receipt_order.append(key)  # Maintain original input order
            delivery_groups[key].append(receipt)
        
        accepted_receipts = []
        duplicate_count = 0
        
        # For each group, determine the accepted receipt and collect duplicates 
        for key in receipt_order:
            group_receipts = delivery_groups[key]
            if len(group_receipts) == 1:
                # Only one receipt for this delivery, it's accepted
                accepted_receipts.append(group_receipts[0])
            else:
                # Multiple receipts for same delivery - need to find the latest (newer timestamp)
                latest_receipt = None
                for receipt in group_receipts:
                    if latest_receipt is None:
                        latest_receipt = receipt
                    else:
                        # Compare timestamps (convert to UTC for comparison)
                        receipt_time = receipt["occurred_at"]
                        latest_time = latest_receipt["occurred_at"]
                        
                        # For RFC3339 timestamps, we can compare as strings since they are in ISO format
                        # If times are equal, compare record_id lexicographically
                        if receipt_time == latest_time:
                            if receipt["record_id"] < latest_receipt["record_id"]:
                                latest_receipt = receipt
                        elif receipt_time > latest_time:
                            latest_receipt = receipt
                
                accepted_receipts.append(latest_receipt)
                duplicate_count += len(group_receipts) - 1
        
        # Return accepted receipts in original input order
        return {
            "protocol": protocol,
            "accepted_count": len(accepted_receipts),
            "duplicate_count": duplicate_count,
            "accepted": accepted_receipts  
        }
    elif q.get("command") == "accepted":
        # Process accepted command according to protocol
        receipts = q.get("receipts", [])
        
        # Handle empty receipts case
        if not receipts:
            return {
                "protocol": protocol,
                "accepted_count": 0,
                "duplicate_count": 0,
                "receipts": []
            }
        
        # For protocol 2, group by (account_id, delivery_id) tuple to identify unique deliveries
        delivery_groups = {}
        receipt_order = []
        for receipt in receipts:
            account_id = receipt["account_id"]
            delivery_id = receipt["delivery_id"]
            key = (account_id, delivery_id)  # Unique identifier per protocol 2
            
            if key not in delivery_groups:
                delivery_groups[key] = []
                receipt_order.append(key)  # Maintain original input order
            delivery_groups[key].append(receipt)
        
        accepted_receipts = []
        duplicate_count = 0
        
        # For each group, determine the accepted receipt and collect duplicates 
        for key in receipt_order:
            group_receipts = delivery_groups[key]
            if len(group_receipts) == 1:
                # Only one receipt for this delivery, it's accepted
                accepted_receipts.append(group_receipts[0])
            else:
                # Multiple receipts for same delivery - need to find the latest (newer timestamp)
                latest_receipt = None
                for receipt in group_receipts:
                    if latest_receipt is None:
                        latest_receipt = receipt
                    else:
                        # Compare timestamps (convert to UTC for comparison)
                        receipt_time = receipt["occurred_at"]
                        latest_time = latest_receipt["occurred_at"]
                        
                        # For RFC3339 timestamps, we can compare as strings since they are in ISO format
                        # If times are equal, compare record_id lexicographically
                        if receipt_time == latest_time:
                            if receipt["record_id"] < latest_receipt["record_id"]:
                                latest_receipt = receipt
                        elif receipt_time > latest_time:
                            latest_receipt = receipt
                
                accepted_receipts.append(latest_receipt)
                duplicate_count += len(group_receipts) - 1
        
        # Return accepted receipts in original input order
        return {
            "protocol": protocol,
            "accepted_count": len(accepted_receipts),
            "duplicate_count": duplicate_count,
            "receipts": accepted_receipts  
        }
    
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
