#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/python3.12/site-packages')
import camoufox
print([m for m in dir(camoufox) if not m.startswith('_')])