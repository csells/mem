"""Trim surrounding whitespace from an opaque identifier."""

import sys


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python id_format.py <identifier>")
    print(sys.argv[1].strip())


if __name__ == "__main__":
    main()
