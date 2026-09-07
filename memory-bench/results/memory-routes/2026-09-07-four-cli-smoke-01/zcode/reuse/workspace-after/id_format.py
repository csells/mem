import sys

if len(sys.argv) != 2:
    sys.exit("usage: id_format.py <identifier>")

print(sys.argv[1].strip())
