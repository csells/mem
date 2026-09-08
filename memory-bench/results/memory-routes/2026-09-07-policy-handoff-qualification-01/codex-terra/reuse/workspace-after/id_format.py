"""Print a supplied opaque identifier with surrounding whitespace removed."""

import sys


if len(sys.argv) == 2:
    print(sys.argv[1].strip())
