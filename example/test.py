#!/usr/bin/python3
import sys
for line in sys.stdin:
	print(line)
print("COOKIE:test2=acbdefg", file=sys.stderr)
#example only effects get requests (eg something.html.py)
print("Cache-Control: no-cache", file=sys.stderr)
