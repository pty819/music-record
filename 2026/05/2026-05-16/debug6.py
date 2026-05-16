import re, html

# Chain D.L.K.: split on " — " separator
text = html.unescape('微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Split on em-dash sequences that are surrounded by whitespace
segments = re.split(r'\s*—\s*', text)
print("Segments:", segments)

for seg in segments:
    # Each segment: "Artist – Album (Label) reviewed by Reviewer of May 12, 2026"
    # Or: "reviewed by Reviewer of May 12, 2026"
    if 'reviewed by' not in seg.lower():
        continue
    # Extract date first
    date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg)
    date_str = date_m.group(1) if date_m else None
    # Remove the "reviewed by..." part to get artist-album-label
    artist_album_part = re.sub(r'reviewed by.*$', '', seg, flags=re.IGNORECASE).strip()
    # Split on en-dash
    if '–' in artist_album_part:
        parts = artist_album_part.split('–', 1)
    else:
        continue
    artist = parts[0].strip()
    rest = parts[1].strip()
    # rest is "Album (Label)"
    label_m = re.search(r'\(([^)]+)\)', rest)
    album = rest
    label = label_m.group(1) if label_m else ''
    if label:
        album = rest[:label_m.start()].strip()
    print(f"  artist={artist!r}, album={album!r}, label={label!r}, date={date_str}")
