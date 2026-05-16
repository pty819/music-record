import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Split on em-dash to get segments
# segments[0] = intro text + first_artist_album
# segments[1] = "reviewed by X of Date A Artist – Album (Label)"
# segments[2] = "reviewed by Y of Date B Artist – Album (Label)"
# segments[3] = "reviewed by Z of Date C"

em_segments = re.split(r'\s*—\s*', text1)
print("Segments:", em_segments)

# For each segment starting from index 1, parse reviewer/date + artist/album
for i in range(1, len(em_segments)):
    seg = em_segments[i].strip()
    print(f"\n--- Seg {i}: {seg[:80]!r}")
    
    # Extract date: "of May 12, 2026"
    date_m = re.search(r'[oO][fF]\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg)
    date_str = date_m.group(1) if date_m else None
    print(f"  date: {date_str}")
    
    # Extract reviewer: everything before " of "
    if date_m:
        reviewer = seg[:date_m.start()].strip()
    else:
        reviewer = re.sub(r'\s*–.*$', '', seg).strip()
    print(f"  reviewer: {reviewer!r}")
    
    # For the artist-album: look at the NEXT segment (i+1) if it exists
    # The artist-album for entry at position i is in segments[i+1]
    if i+1 < len(em_segments):
        next_seg = em_segments[i+1].strip()
        print(f"  next_seg: {next_seg[:80]!r}")
        # Parse Artist – Album (Label) from next_seg
        artist_album_m = re.match(
            r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$',
            next_seg
        )
        if artist_album_m:
            artist, album, label = artist_album_m.groups()
            print(f"  FOUND: artist={artist.strip()!r}, album={album.strip()!r}, label={label.strip()!r}")
