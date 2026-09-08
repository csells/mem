#!/usr/bin/env python3
"""Print a single identifier argument with surrounding whitespace removed.

Leading zeros and letter case are preserved; only leading and trailing
whitespace is stripped.
"""
import sys


def format_id(value: str) -> str:
    return value.strip()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: id_format.py <identifier>\n")
        return 2
    print(format_id(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
