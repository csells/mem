#!/usr/bin/env python3
"""HarborPass JSON command-line application."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "HarborPass"}
    return {"error": "unknown_command"}


def main():
    request = json.load(sys.stdin)
    response = handle(request)
    json.dump(response, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
