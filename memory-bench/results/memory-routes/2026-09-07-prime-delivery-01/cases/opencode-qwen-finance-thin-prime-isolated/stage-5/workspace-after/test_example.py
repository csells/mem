#!/usr/bin/env python3
import json
import subprocess
import sys

# Test the specific example from the issue description
example_request = {
    "command": "quote", 
    "line": {
        "line_id": "L-1", 
        "account_id": "A", 
        "subscription_id": "S", 
        "service_on": "2026-04-15",  
        "charge_cents": 19999
    }
}

# Test with release 2.0 (should get the exact expected result from issue)
example_request["release"] = "2.0"

proc = subprocess.run([sys.executable, "main.py"], 
                      input=json.dumps(example_request),
                      capture_output=True, text=True, check=True)

result = json.loads(proc.stdout.strip())
expected = {
    "release": "2.0", 
    "credit_cents": 2999, 
    "amount_due_cents": 17000, 
    "line_id": "L-1"
}

print("Result:", result)
print("Expected:", expected)
print("Match:", result == expected)