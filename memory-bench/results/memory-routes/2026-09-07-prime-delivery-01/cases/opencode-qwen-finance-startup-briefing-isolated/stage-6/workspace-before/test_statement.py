#!/usr/bin/env python3

import json
import subprocess
import sys

def test_statement():
    # Test case 1: Empty lines
    result = subprocess.run([
        sys.executable, "main.py"
    ], input=json.dumps({
        "command": "statement",
        "lines": []
    }), text=True, capture_output=True, check=True)
    
    expected = {
        "release": "2.0",
        "lines": [],
        "credit_cents": 0,
        "amount_due_cents": 0
    }
    
    actual = json.loads(result.stdout)
    print("Test 1 - Empty lines:")
    print("Expected:", expected)
    print("Actual:  ", actual)
    assert actual == expected, f"Expected {expected}, got {actual}"
    print("✓ PASS\n")
    
    # Test case 2: Single line
    result = subprocess.run([
        sys.executable, "main.py"
    ], input=json.dumps({
        "command": "statement",
        "lines": [{
            "line_id": "L-1",
            "account_id": "A-1",
            "subscription_id": "S-1",
            "service_on": "2024-01-01",
            "charge_cents": 10000
        }]
    }), text=True, capture_output=True, check=True)
    
    # With 15% credit (1500) for 10000 cents charge
    expected = {
        "release": "2.0",
        "lines": [{
            "line_id": "L-1",
            "credit_cents": 1500,
            "amount_due_cents": 8500
        }],
        "credit_cents": 1500,
        "amount_due_cents": 8500
    }
    
    actual = json.loads(result.stdout)
    print("Test 2 - Single line:")
    print("Expected:", expected)
    print("Actual:  ", actual)
    assert actual == expected, f"Expected {expected}, got {actual}"
    print("✓ PASS\n")

if __name__ == "__main__":
    test_statement()
    print("All tests passed!")