#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    elif q.get("command") == "accepted":
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
            # For protocol 2: (account_id, delivery_id) identifies a delivery
            # Exactly one receipt is accepted per delivery identity - the one with latest occurred_at UTC instant 
            # Equal instants use smallest record_id
            # Initialize counters
            accepted_count = 0
            duplicate_count = 0
            
            # Dictionary to store the best receipt for each (account_id, delivery_id) tuple
            delivery_map = {}
            
            # Process each receipt
            for receipt in receipts:
                account_id = receipt["account_id"]
                delivery_id = receipt["delivery_id"]
                record_id = receipt["record_id"]
                occurred_at_str = receipt["occurred_at"]
                
                # Parse timestamp and convert to UTC
                dt = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                
                # Create delivery key as tuple of (account_id, delivery_id)
                delivery_key = (account_id, delivery_id)
                
                if delivery_key not in delivery_map:
                    # First receipt for this delivery
                    delivery_map[delivery_key] = {
                        "receipt": receipt,
                        "timestamp": dt,
                        "record_id": record_id
                    }
                    accepted_count += 1
                else:
                    # Check if this is better than the existing one
                    existing = delivery_map[delivery_key]
                    
                    # Compare timestamps
                    if dt > existing["timestamp"] or \
                       (dt == existing["timestamp"] and record_id < existing["record_id"]):
                        # This receipt is better, so we mark the old one as duplicate
                        duplicate_count += 1
                        delivery_map[delivery_key] = {
                            "receipt": receipt,
                            "timestamp": dt,
                            "record_id": record_id
                        }
                    else:
                        # Existing receipt is better, mark this one as duplicate
                        duplicate_count += 1
            
            # Build the response with receipts in original order
            accepted_receipts = []
            for receipt in receipts:
                account_id = receipt["account_id"]
                delivery_id = receipt["delivery_id"]
                delivery_key = (account_id, delivery_id)
                
                # Check if this receipt is the one that was accepted for its delivery
                if delivery_key in delivery_map and delivery_map[delivery_key]["receipt"] is receipt:
                    accepted_receipts.append(receipt)
            
            return {
                "protocol": protocol,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count,
                "receipts": accepted_receipts
            }
        
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
