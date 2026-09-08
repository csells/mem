#!/usr/bin/env python3

import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} IDENTIFIER")

    print(sys.argv[1].strip())


if __name__ == "__main__":
    main()
