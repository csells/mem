#!/usr/bin/env python3
"""Print one identifier with surrounding whitespace removed."""

import sys


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} IDENTIFIER", file=sys.stderr)
        return 2

    print(sys.argv[1].strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
