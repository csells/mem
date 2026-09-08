#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") == "accepted":
        # Determine protocol version
        protocol = q.get("protocol", "2")
        
        receipts = q.get("receipts", [])
        
        # Keep original order of receipts for output
        original_receipts = receipts[:]
        
        if protocol == "1":
            # Protocol 1: delivery_id alone identifies a delivery across all accounts
            # Accept the receipt with the earliest occurred_at UTC instant; equal instants use the smallest record_id
            # All other receipts for that identity are duplicates
            
            # Group receipts by delivery_id
            delivery_groups = {}
            for receipt in receipts:
                delivery_id = receipt.get("delivery_id")
                if delivery_id not in delivery_groups:
                    delivery_groups[delivery_id] = []
                delivery_groups[delivery_id].append(receipt)
            
            accepted_count = 0
            duplicate_count = 0
            accepted_receipts = []
            
            # Process each group of receipts with the same delivery_id
            for delivery_id, group in delivery_groups.items():
                if len(group) == 1:
                    # Only one receipt for this delivery_id - it's accepted
                    accepted_count += 1
                    accepted_receipts.append(group[0])
                else:
                    # Multiple receipts for this delivery_id - need to determine which is accepted
                    # Sort by occurred_at first (earliest first), then by record_id for ties
                    group.sort(key=lambda r: (r.get("occurred_at"), r.get("record_id")))
                    
                    # First one in sorted list is accepted, others are duplicates
                    accepted_count += 1
                    duplicate_count += len(group) - 1
                    accepted_receipts.append(group[0])
            
            # Return receipts in the original input order
            receipt_map = {r["record_id"]: r for r in original_receipts}
            ordered_accepted_receipts = [receipt_map[r["record_id"]] for r in accepted_receipts if r["record_id"] in receipt_map]
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count,
                "receipts": ordered_accepted_receipts
            }
        elif protocol == "2":
            # Protocol 2: (account_id, delivery_id) identifies a delivery
            # Accept the receipt with the latest occurred_at UTC instant; equal instants use the smallest record_id
            # All other receipts for that identity are duplicates
            
            # Group receipts by (account_id, delivery_id)
            delivery_groups = {}
            for receipt in receipts:
                account_id = receipt.get("account_id")
                delivery_id = receipt.get("delivery_id")
                key = (account_id, delivery_id)
                if key not in delivery_groups:
                    delivery_groups[key] = []
                delivery_groups[key].append(receipt)
            
            accepted_count = 0
            duplicate_count = 0
            accepted_receipts = []
            
            # Process each group of receipts with the same (account_id, delivery_id)
            for key, group in delivery_groups.items():
                if len(group) == 1:
                    # Only one receipt for this delivery - it's accepted
                    accepted_count += 1
                    accepted_receipts.append(group[0])
                else:
                    # Multiple receipts for this delivery - need to determine which is accepted
                    # Sort by occurred_at descending (latest first), then by record_id ascending for ties
                    group.sort(key=lambda r: (r.get("occurred_at"), r.get("record_id")), reverse=True)
                    
                    # First one in sorted list is accepted, others are duplicates
                    accepted_count += 1
                    duplicate_count += len(group) - 1
                    accepted_receipts.append(group[0])
            
            # Return receipts in the original input order
            receipt_map = {r["record_id"]: r for r in original_receipts}
            ordered_accepted_receipts = [receipt_map[r["record_id"]] for r in accepted_receipts if r["record_id"] in receipt_map]
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count,
                "receipts": ordered_accepted_receipts
            }
    elif q.get("command") in ("count", "summary"):
        # Determine protocol version
        protocol = q.get("protocol", "2")
        
        receipts = q.get("receipts", [])
        
        if protocol == "1":
            # Protocol 1: delivery_id alone identifies a delivery across all accounts
            # Accept the receipt with the earliest occurred_at UTC instant; equal instants use the smallest record_id
            # All other receipts for that identity are duplicates
            
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
                    # Sort by occurred_at first (earliest first), then by record_id for ties
                    group.sort(key=lambda r: (r.get("occurred_at"), r.get("record_id")))
                    
                    # First one in sorted list is accepted, others are duplicates
                    accepted_count += 1
                    duplicate_count += len(group) - 1
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count
            }
        elif protocol == "2":
            # Protocol 2: (account_id, delivery_id) identifies a delivery
            # Accept the receipt with the latest occurred_at UTC instant; equal instants use the smallest record_id
            # All other receipts for that identity are duplicates
            
            # Group receipts by (account_id, delivery_id)
            delivery_groups = {}
            for receipt in receipts:
                account_id = receipt.get("account_id")
                delivery_id = receipt.get("delivery_id")
                key = (account_id, delivery_id)
                if key not in delivery_groups:
                    delivery_groups[key] = []
                delivery_groups[key].append(receipt)
            
            accepted_count = 0
            duplicate_count = 0
            
            # Process each group of receipts with the same (account_id, delivery_id)
            for key, group in delivery_groups.items():
                if len(group) == 1:
                    # Only one receipt for this delivery - it's accepted
                    accepted_count += 1
                else:
                    # Multiple receipts for this delivery - need to determine which is accepted
                    # Sort by occurred_at descending (latest first), then by record_id ascending for ties
                    # For descending order, we can reverse the sort or use negative key values in a way that works with strings
                    # Since timestamps are RFC3339 formatted, string comparison actually works correctly 
                    group.sort(key=lambda r: (r.get("occurred_at"), r.get("record_id")), reverse=True)
                    
                    # First one in sorted list is accepted, others are duplicates
                    accepted_count += 1
                    duplicate_count += len(group) - 1
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count
            }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
