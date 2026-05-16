import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Split on em-dash surrounded by spaces
segments = re.split(r'\s*—\s*', text1)
print("Chain D.L.K. segments:", segments)

# Now process each segment
for seg in segments:
    seg = seg.strip()
    if not seg or 'reviewed by' not in seg.lower():
        print(f"  SKIP: {seg[:60]}")
        continue
    date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg)
    inline_date = date_m.group(1) if date_m else None
    artist_album_label = re.sub(r'\s*reviewed by.*$', '', seg, flags=re.IGNORECASE).strip()
    print(f"  after strip: {artist_album_label!r}")
    if '–' not in artist_album_label:
        print(f"  NO DASH: {artist_album_label[:40]}")
        continue
    parts = artist_album_label.split('–', 1)
    artist = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    print(f"  artist={artist!r}, rest={rest!r}")
    label_m = re.search(r'\(([^)]+)\)', rest)
    if not label_m:
        print(f"  NO LABEL")
        continue
    album = rest[:label_m.start()].strip()
    label = label_m.group(1).strip()
    print(f"  artist={artist!r}, album={album!r}, label={label!r}, date={inline_date}")
