#!/usr/bin/env python3
"""Inspect one item's full body for quality."""
import json

d = json.load(open("boomkat_reviews.json"))
for i in d["items"]:
    if i["album"] == "End Credits Noumena":
        print(f"artist: {i['artist']!r}\nalbum: {i['album']!r}\ntags: {i['tags']!r}\nurl: {i['url']}\nexcerpt[:200]: {i['excerpt'][:200]!r}\n\nFULL BODY:\n{i['body']}")
