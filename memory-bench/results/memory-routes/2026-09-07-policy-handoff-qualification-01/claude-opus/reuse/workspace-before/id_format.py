#!/usr/bin/env python3
"""Print an identifier with surrounding whitespace removed.

Identifiers are opaque strings: leading zeros and case are preserved.
"""

import sys


def format_identifier(value):
    """Return the identifier with surrounding whitespace stripped."""
    return value.strip()


def main(argv):
    if len(argv) != 2:
        print("usage: id_format.py <identifier>", file=sys.stderr)
        return 1
    print(format_identifier(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
