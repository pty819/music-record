#!/usr/bin/env python3
"""Classify boomkat item bodies: real editorial prose vs cart/price widget junk."""
import json
import re

JUNK_MARKERS = ("Add to crate", "Play All", "MP3 Release", "Vinyl LP", "£")


def junk_score(body: str) -> float:
    """Fraction of lines that look like widget chrome (short/blank/price)."""
    lines = [ln.strip() for ln in body.splitlines()]
    nonblank = [ln for ln in lines if ln]
    if not nonblank:
        return 1.0
    chrome = sum(
        1
        for ln in nonblank
        if len(ln) < 30 or ln.startswith("£") or "Add to crate" in ln
    )
    return chrome / len(nonblank)


d = json.load(open("boomkat_reviews.json"))
it = d["items"]
bad = []
for n, i in enumerate(it):
    b = i.get("body") or ""
    # a real review has at least one long prose paragraph
    prose = [p.strip() for p in b.split("\n") if len(p.strip()) > 120]
    js = junk_score(b)
    if not prose or js > 0.75:
        bad.append((n, i.get("album"), i.get("url"), len(b), round(js, 2), len(prose)))

print("total:", len(it), "junk-body:", len(bad))
for row in bad:
    print("  ", row[0], "|", row[1], "| len", row[3], "| junk", row[4], "| prose_paras", row[5])
    print("      ", row[2])
