#!/usr/bin/env python3
"""Test the quote functionality."""
import json
import subprocess
import sys

def test_quote():
    # Test case from the issue description
    test_input = {
        "command": "quote",
        "release": "1.0", 
        "line": {
            "line_id": "L-1",
            "account_id": "A",
            "subscription_id": "S",
            "service_on": "2026-04-15",
            "charge_cents": 19999
        }
    }
    
    # Run the CLI with test input
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(test_input))
    
    if process.returncode != 0:
        print(f"Error running CLI: {stderr}")
        return False
    
    try:
        result = json.loads(stdout.strip())
        expected = {
            "release": "1.0",
            "credit_cents": 1999,
            "amount_due_cents": 18000,
            "line_id": "L-1"
        }
        
        if result == expected:
            print("✅ Test passed!")
            print(f"Input: {test_input}")
            print(f"Output: {result}")
            return True
        else:
            print("❌ Test failed!")
            print(f"Expected: {expected}")
            print(f"Got: {result}")
            return False
            
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Output: {stdout}")
        return False

def test_ping():
    """Test ping command still works."""
    test_input = {"command": "ping"}
    
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(test_input))
    
    if process.returncode != 0:
        print(f"Error running CLI: {stderr}")
        return False
    
    try:
        result = json.loads(stdout.strip())
        expected = {"status": "ok", "product": "Meridian Credits"}
        
        if result == expected:
            print("✅ Ping test passed!")
            return True
        else:
            print("❌ Ping test failed!")
            print(f"Expected: {expected}")
            print(f"Got: {result}")
            return False
            
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return False

if __name__ == "__main__":
    success = True
    success &= test_ping()
    success &= test_quote()
    
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)