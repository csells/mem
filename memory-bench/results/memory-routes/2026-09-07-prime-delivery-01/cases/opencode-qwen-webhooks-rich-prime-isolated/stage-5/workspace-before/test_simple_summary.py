#!/usr/bin/env python3
import json
import sys
sys.path.append('.')

from main import run

# Test with protocol 2, summary command
test_input = {
    "command": "summary",
    "protocol": "2",
    "receipts": [
        {
            "record_id": "R-1",
            "account_id": "A", 
            "delivery_id": "D-1",
            "occurred_at": "2026-04-01T10:00:00Z",
            "payload": "payload:R-1"
        }
    ]
}

result = run(test_input)
print(json.dumps(result, indent=2))