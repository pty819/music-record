import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Split on ' — reviewed by' (em-dash + space + reviewed by)
# This gives us:
# segments[0] = intro + artist_album (first entry, has no preceding reviewer)
# segments[1] = 'Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion)'
# segments[2] = 'Vito Camarretta of May 11, 2026'
em_segments = re.split(r'\s*—\s*reviewed by\s*', text1, flags=re.IGNORECASE)
print("Segments:")
for i, s in enumerate(em_segments):
    print(f"  [{i}]: {s[:80]!r}")

print()

# For Chain D.L.K.:
# segments[0] = intro + first_artist_album
# segments[1] = 'Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion)'
# segments[2] = 'Vito Camarretta of May 11, 2026'
# 
# Processing:
# - Entry 0: artist_album from segments[0], reviewer from segments[1]
# - Entry 1: artist_album from segments[1] (after date), reviewer from segments[2]

results = []

# Entry 0: artist-album from end of segments[0], reviewer from start of segments[1]
artist_album_part = em_segments[0]
# Extract the artist-album from the end of segments[0]
aa_m = re.search(r'([^\u2014—]+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$', artist_album_part)
if aa_m:
    artist0, album0, label0 = aa_m.groups()
    print(f"Entry 0: artist={artist0.strip()!r}, album={album0.strip()!r}, label={label0.strip()!r}")

# reviewer from segments[1]
if len(em_segments) > 1:
    seg1 = em_segments[1]
    date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg1, re.IGNORECASE)
    date0 = date_m.group(1) if date_m else None
    reviewer0 = re.sub(r'\s*of.*$', '', seg1, flags=re.IGNORECASE).strip()
    print(f"Entry 0 reviewer: {reviewer0!r}, date: {date0!r}")
    # artist for entry 0:
    # Also extract artist for next entry from seg1
    remainder = seg1[date_m.end():].strip() if date_m else seg1
    aa1_m = re.match(r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)', remainder)
    if aa1_m:
        artist1, album1, label1 = aa1_m.groups()
        print(f"Entry 1: artist={artist1.strip()!r}, album={album1.strip()!r}, label={label1.strip()!r}")

# Entry 1: from segments[2] (if it exists)
if len(em_segments) > 2:
    seg2 = em_segments[2]
    date_m2 = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg2, re.IGNORECASE)
    date1 = date_m2.group(1) if date_m2 else None
    reviewer1 = re.sub(r'\s*of.*$', '', seg2, flags=re.IGNORECASE).strip()
    print(f"Entry 1 reviewer: {reviewer1!r}, date: {date1!r}")
