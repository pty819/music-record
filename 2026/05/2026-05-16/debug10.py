import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Strategy: pair artist-album segments with the FOLLOWING reviewer-date segment
# Split on em-dash
parts = re.split(r'\s*—\s*', text1)
print("Parts:", parts)

# parts[0] = intro + artist-album-1
# parts[1] = "reviewed by X of date A artist-album-2"
# parts[2] = "reviewed by Y of date B artist-album-3"
# ...

# Process: for i from 0, skip until we find "reviewed by", then pair with next
# Better: look for all "reviewed by X of DATE" occurrences and grab the preceding artist-album

# Find all occurrences of "reviewed by" with their positions
reviewed_positions = [(m.start(), m.group()) for m in re.finditer(r'reviewed by', text1, re.IGNORECASE)]
print("Review positions:", reviewed_positions)

# Extract segments between "Artist – Album (Label)" and "reviewed by"
# Split at each " — " to get alternating [intro/artist-part, reviewer-part]
em_segments = re.split(r'\s*—\s*', text1)
print("em_segments:", em_segments)

# Pair each artist-album segment with the NEXT segment that has "reviewed by"
i = 0
while i < len(em_segments):
    seg = em_segments[i].strip()
    if not seg:
        i += 1
        continue
    # Check if this seg has an artist-album pattern: Artist – Album (Label)
    has_dash = bool(re.search(r'–\s*[^—]+', seg))
    has_paren = bool(re.search(r'\([^)]{2,}\)', seg))
    if has_dash and has_paren and 'reviewed by' not in seg.lower():
        # This is an artist-album segment - look for reviewer in NEXT segment
        if i+1 < len(em_segments):
            next_seg = em_segments[i+1].strip()
            if 'reviewed by' in next_seg.lower():
                date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', next_seg)
                rev_m  = re.search(r'reviewed by\s+([^,]+)', next_seg, re.IGNORECASE)
                artist_album_part = seg
                artist_m = re.match(r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$', artist_album_part.strip())
                if artist_m:
                    artist, album, label = artist_m.groups()
                    print(f"FOUND: artist={artist.strip()!r}, album={album.strip()!r}, label={label.strip()!r}, date={date_m.group(1) if date_m else None}, reviewer={rev_m.group(1).strip() if rev_m else None}")
                    i += 2
                    continue
    i += 1
