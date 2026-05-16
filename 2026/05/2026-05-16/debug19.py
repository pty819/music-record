import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

def parse_chain_dlk(text):
    """
    Split on ' — reviewed by'. Each segment S[i] contains:
      - For i=0: artist-album of entry[0] (at the very end of S[0])
      - For i>=1: "Reviewer of Date Artist – Album (Label)" for entry[i-1]
                   PLUS artist-album of entry[i] if i < len(S)-1
    """
    # Split on ' — reviewed by'
    raw_segments = re.split(r'\s*—\s*reviewed by\s*', text, flags=re.IGNORECASE)
    results = []
    
    # Process segments: for i=0, extract artist-album from end of raw_segments[0]
    # for i>=1, extract reviewer+date from start of raw_segments[i], 
    #             and artist-album from end of raw_segments[i] (if not last)
    
    for i in range(len(raw_segments)):
        seg = raw_segments[i]
        
        if i == 0:
            # Extract artist-album from the END of seg (after last em-dash)
            # Split seg on em-dashes to get the last artist-album part
            parts = re.split(r'\s*—\s*', seg)
            artist_album_part = parts[-1].strip()
            # Now extract artist – album (label) from artist_album_part
            # e.g., "微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu)"
            artist_album_m = re.match(
                r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$',
                artist_album_part
            )
            if not artist_album_m:
                continue
            artist, album, label = artist_album_m.groups()
            # Get reviewer+date from raw_segments[1]
            if len(raw_segments) > 1:
                next_seg = raw_segments[1]
                reviewer, date = _extract_reviewer_date(next_seg)
            else:
                reviewer, date = None, None
            results.append({
                'artist': artist.strip(),
                'album': album.strip(),
                'label': label.strip(),
                'reviewer': (reviewer or '').strip(),
                'date': (date or '').strip()
            })
        else:
            # seg = "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion)"
            # OR for last segment: "Vito Camarretta of May 11, 2026"
            reviewer, date = _extract_reviewer_date(seg)
            
            # Extract artist-album from the END of seg (the artist-album for THIS entry)
            # Split on em-dash to get the artist-album part
            sub_parts = re.split(r'\s*—\s*', seg)
            artist_album_part = sub_parts[-1].strip()
            artist_album_m = re.match(
                r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$',
                artist_album_part
            )
            if artist_album_m:
                artist, album, label = artist_album_m.groups()
                results.append({
                    'artist': artist.strip(),
                    'album': album.strip(),
                    'label': label.strip(),
                    'reviewer': (reviewer or '').strip(),
                    'date': (date or '').strip()
                })
    
    return results

def _extract_reviewer_date(seg):
    """Extract reviewer name and date from start of segment."""
    # "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II..."
    date_m = re.search(r'[oO][fF]\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', seg)
    date_str = date_m.group(1) if date_m else None
    if date_m:
        # Reviewer is everything before 'of'
        reviewer = seg[:date_m.start()].strip()
    else:
        # No date, reviewer is everything up to first em-dash or end
        reviewer = re.sub(r'\s*—.*$', '', seg).strip()
    return reviewer, date_str

for r in parse_chain_dlk(text1):
    print(f"  artist={r['artist']!r}, album={r['album']!r}, label={r['label']!r}, reviewer={r['reviewer']!r}, date={r['date']!r}")
