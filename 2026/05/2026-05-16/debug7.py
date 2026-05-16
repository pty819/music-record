import re, html

# Free Jazz Collective
text = html.unescape('Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

# Split on period + space + capital letter (entry boundary)
entries = re.split(r'\.\s+(?=[A-Z])', text)
print("Entries:", entries)

for entry in entries:
    if not entry.strip():
        continue
    # "reviewed by X"
    rev_m = re.search(r'reviewed by\s+([^.]+)', entry, re.IGNORECASE)
    reviewer = rev_m.group(1).strip() if rev_m else None
    # artist – album (label_year)
    # The artist is everything before the dash, stripped of trailing parentheticals
    dash_m = re.search(r'\s*[–—]\s*', entry)
    if not dash_m:
        continue
    artist_full = entry[:dash_m.start()].strip()
    after = entry[dash_m.end():].strip()
    # Remove reviewer suffix
    if reviewer:
        after = re.sub(r'\s*reviewed by.*$', '', after, flags=re.IGNORECASE).strip()
    # after = "Album (Label, Year)"
    paren_m = re.search(r'\(([^)]+)\)', after)
    album = after
    label_year = ''
    if paren_m:
        label_year = paren_m.group(1)
        album = after[:paren_m.start()].strip()
    # Strip trailing parenthetical from artist
    artist = re.sub(r'\s*\([^)]*\)\s*$', '', artist_full).strip()
    print(f"  artist={artist!r}, album={album!r}, label={label_year!r}, reviewer={reviewer!r}")
