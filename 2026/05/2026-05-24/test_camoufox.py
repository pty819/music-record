#!/usr/bin/env python3
import sys
print("Python:", sys.version)

try:
    from camoufox import Browser
    print("camoufox Browser imported OK")
    b = Browser(headless=True, print_return_value=False)
    print("Browser created")
    p = b.new_page()
    print("Page created, methods:", [x for x in dir(p) if not x.startswith('_')][:15])
    b.close()
    print("Done")
except Exception as e:
    print("ERROR:", e)
    import traceback
    traceback.print_exc()