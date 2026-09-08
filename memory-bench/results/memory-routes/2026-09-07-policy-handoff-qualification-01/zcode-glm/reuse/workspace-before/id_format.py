#!/usr/bin/env python3
"""Print a single argument with surrounding whitespace removed.

Identifiers are opaque strings: leading zeros and case are preserved.
"""
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: id_format.py <identifier>", file=sys.stderr)
        return 2
    print(sys.argv[1].strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
