#!/usr/bin/env python3
import json
import subprocess
import sys

# Test case with duplicates to verify the summary function works correctly
test_input = {
    "command": "summary",
    "protocol": "1",
    "receipts": [
        {
            "record_id": "R-1",
            "account_id": "A",
            "delivery_id": "D-1",
            "occurred_at": "2026-04-01T10:00:00Z",
            "payload": "payload:R-1"
        },
        {
            "record_id": "R-2", 
            "account_id": "B",
            "delivery_id": "D-1",
            "occurred_at": "2026-04-01T09:00:00Z",
            "payload": "payload:R-2"
        },
        {
            "record_id": "R-3",
            "account_id": "C", 
            "delivery_id": "D-2",
            "occurred_at": "2026-04-01T11:00:00Z",
            "payload": "payload:R-3"
        }
    ]
}

result = subprocess.run([sys.executable, "main.py"], 
                       input=json.dumps(test_input), 
                       capture_output=True, 
                       text=True)
                       
print("Input:", json.dumps(test_input, indent=2))
print("Output:", result.stdout.strip())