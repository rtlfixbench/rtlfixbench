import sys
from defaults import *

def show(s):
    if VERBOSE:
        print(f'> {s}')

def info(s):
    if VERBOSE:
        print(f'[RTLFIXBENCH] {s}')

def err(s):
    print(f'Error: {s}')
    sys.exit(-1)

def warn(s):
    if WARNING:
        print(f'[RTLFIXBENCH] {s}')
