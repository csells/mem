#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") == "count":
        # Protocol 1: delivery_id alone identifies a delivery across all accounts
        # Accept the receipt with earliest occurred_at UTC instant; equal instants use smallest record_id
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        
        # Group receipts by delivery_id
        delivery_map = {}
        for receipt in receipts:
            delivery_id = receipt["delivery_id"]
            if delivery_id not in delivery_map:
                delivery_map[delivery_id] = []
            delivery_map[delivery_id].append(receipt)
        
        accepted_count = 0
        duplicate_count = 0
        
        # For each delivery, select the accepted receipt
        for delivery_id, delivery_receipts in delivery_map.items():
            if not delivery_receipts:
                continue
                
            # Sort by occurred_at (UTC instant) then by record_id
            delivery_receipts.sort(key=lambda r: (r["occurred_at"], r["record_id"]))
            
            # First receipt is the accepted one
            accepted_receipt = delivery_receipts[0]
            accepted_count += 1
            
            # All remaining receipts are duplicates
            duplicate_count += len(delivery_receipts) - 1
        
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    elif q.get("command") == "summary":
        # Protocol 1: delivery_id alone identifies a delivery across all accounts
        # Accept the receipt with earliest occurred_at UTC instant; equal instants use smallest record_id
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        
        # Group receipts by delivery_id
        delivery_map = {}
        for receipt in receipts:
            delivery_id = receipt["delivery_id"]
            if delivery_id not in delivery_map:
                delivery_map[delivery_id] = []
            delivery_map[delivery_id].append(receipt)
        
        accepted_count = 0
        duplicate_count = 0
        
        # For each delivery, select the accepted receipt
        for delivery_id, delivery_receipts in delivery_map.items():
            if not delivery_receipts:
                continue
                
            # Sort by occurred_at (UTC instant) then by record_id
            delivery_receipts.sort(key=lambda r: (r["occurred_at"], r["record_id"]))
            
            # First receipt is the accepted one
            accepted_receipt = delivery_receipts[0]
            accepted_count += 1
            
            # All remaining receipts are duplicates
            duplicate_count += len(delivery_receipts) - 1
        
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }
    elif q.get("command") == "accepted":
        # Protocol 1: delivery_id alone identifies a delivery across all accounts
        # Protocol 2: account_id + delivery_id identifies a delivery
        # Accept the receipt with earliest occurred_at UTC instant; equal instants use smallest record_id
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        
        # Group receipts by appropriate identifier based on protocol
        delivery_map = {}
        for receipt in receipts:
            if protocol == "2":
                # Protocol 2: account_id + delivery_id identifies a delivery
                key = (receipt["account_id"], receipt["delivery_id"])
            else:
                # Protocol 1: delivery_id alone identifies a delivery
                key = receipt["delivery_id"]
            
            if key not in delivery_map:
                delivery_map[key] = []
            delivery_map[key].append(receipt)
        
        accepted_count = 0
        duplicate_count = 0
        
        # For each delivery, select the accepted receipt
        accepted_receipts = []
        for key, delivery_receipts in delivery_map.items():
            if not delivery_receipts:
                continue
                
            # Sort by occurred_at (UTC instant) then by record_id
            delivery_receipts.sort(key=lambda r: (r["occurred_at"], r["record_id"]))
            
            # First receipt is the accepted one
            accepted_receipt = delivery_receipts[0]
            accepted_count += 1
            accepted_receipts.append(accepted_receipt)
            
            # All remaining receipts are duplicates
            duplicate_count += len(delivery_receipts) - 1
        
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
            "receipts": accepted_receipts
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
