import json
import subprocess
import sys

test_cases = [
    {
        "name": "protocol2_different_accounts_same_delivery",
        "request": {
            "command": "count",
            "protocol": "2",
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
                    "occurred_at": "2026-04-01T11:00:00Z",
                    "payload": "payload:R-2"
                }
            ]
        },
        "expected": {
            "protocol": "2",
            "accepted_count": 1,
            "duplicate_count": 1
        }
    },
    {
        "name": "protocol1_different_accounts_same_delivery",
        "request": {
            "command": "count",
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
                    "occurred_at": "2026-04-01T11:00:00Z",
                    "payload": "payload:R-2"
                }
            ]
        },
        "expected": {
            "protocol": "1",
            "accepted_count": 2,
            "duplicate_count": 0
        }
    }
]

for test_case in test_cases:
    proc = subprocess.run([sys.executable, "main.py"],
                          input=json.dumps(test_case["request"]),
                          capture_output=True, text=True, check=True, timeout=5)
    got = json.loads(proc.stdout)
    if got == test_case["expected"]:
        print(f"PASS {test_case['name']}")
    else:
        print(f"FAIL {test_case['name']}")
        print(f"  expected: {test_case['expected']}")
        print(f"  got: {got}")
