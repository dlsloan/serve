#!/usr/bin/python3
import sys
import os
print(sys.argv)
os.environ['COOKIE_test2'] = 'abcdefg'
#example only effects get requests (eg something.html.py)
os.environ['CACHE_CONTROL'] = 'no-cache'
