"""Trim surrounding whitespace from an opaque identifier."""

import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier")
    args = parser.parse_args()
    print(args.identifier.strip())


if __name__ == "__main__":
    main()
