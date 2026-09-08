#!/usr/bin/env python3

import sys

if len(sys.argv) != 2:
    print("Usage: python id_format.py <id>")
    sys.exit(1)

id_value = sys.argv[1]
print(id_value.strip())