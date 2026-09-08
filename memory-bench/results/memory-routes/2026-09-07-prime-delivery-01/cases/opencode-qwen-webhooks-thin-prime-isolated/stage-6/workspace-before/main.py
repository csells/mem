#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") == "count":
        receipts = q.get("receipts", [])
        protocol = q.get("protocol", "2")
        
        # Handle protocol 1 specifically
        if protocol == "1":
            # For protocol 1, return the list of accepted receipts with their details
            # Using original provider contract - no counting, just filtering by delivery_id uniqueness
            delivery_map = {}
            accepted_receipts = []
            
            # Process each receipt maintaining order
            for receipt in receipts:
                delivery_id = receipt["delivery_id"]
                record_id = receipt["record_id"]
                occurred_at_str = receipt["occurred_at"]
                
                # Parse timestamp and convert to UTC
                dt = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                
                if delivery_id not in delivery_map:
                    # First receipt for this delivery - accept it
                    delivery_map[delivery_id] = {
                        "receipt": receipt,
                        "timestamp": dt,
                        "record_id": record_id
                    }
                    accepted_receipts.append(receipt)
                else:
                    # Check if this is better than the existing one
                    existing = delivery_map[delivery_id]
                    
                    # Compare timestamps
                    if dt < existing["timestamp"] or \
                       (dt == existing["timestamp"] and record_id < existing["record_id"]):
                        # This receipt is better, replace the existing one
                        delivery_map[delivery_id] = {
                            "receipt": receipt,
                            "timestamp": dt,
                            "record_id": record_id
                        }
                        # Find index of old receipt and replace it
                        for i, r in enumerate(accepted_receipts):
                            if r["delivery_id"] == delivery_id:
                                accepted_receipts[i] = receipt
                                break
            
            return {
                "protocol": protocol,
                "receipts": accepted_receipts
            }
        else:
            # For protocol 2 and other versions, maintain existing behavior
            # Initialize counters
            accepted_count = 0
            duplicate_count = 0
            
            # Dictionary to store the best receipt for each delivery_id
            delivery_map = {}
            
            # Process each receipt
            for receipt in receipts:
                delivery_id = receipt["delivery_id"]
                record_id = receipt["record_id"]
                occurred_at_str = receipt["occurred_at"]
                
                # Parse timestamp and convert to UTC
                dt = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                
                if delivery_id not in delivery_map:
                    # First receipt for this delivery
                    delivery_map[delivery_id] = {
                        "receipt": receipt,
                        "timestamp": dt,
                        "record_id": record_id
                    }
                    accepted_count += 1
                else:
                    # Check if this is better than the existing one
                    existing = delivery_map[delivery_id]
                    
                    # Compare timestamps
                    if dt < existing["timestamp"] or \
                       (dt == existing["timestamp"] and record_id < existing["record_id"]):
                        # This receipt is better, so we mark the old one as duplicate
                        duplicate_count += 1
                        delivery_map[delivery_id] = {
                            "receipt": receipt,
                            "timestamp": dt,
                            "record_id": record_id
                        }
                    else:
                        # Existing receipt is better, mark this one as duplicate
                        duplicate_count += 1
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count
            }
        
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
