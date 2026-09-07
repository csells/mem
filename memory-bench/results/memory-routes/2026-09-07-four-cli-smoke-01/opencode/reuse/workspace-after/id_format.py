#!/usr/bin/env python3

import sys

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: id_format.py <string>")
        sys.exit(1)
    
    input_string = sys.argv[1]
    result = input_string.strip()
    print(result)