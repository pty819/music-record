import re, html

# Chain D.L.K.
text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

def parse_chain_dlk(text):
    """
    Strategy: iterate through text with a cursor.
    Each review: "Artist – Album (Label) — reviewed by Reviewer of Date [next Artist...]"
    We scan for " — reviewed by", extract Artist-Album-Label from what precedes it,
    and extract Reviewer+Date from what follows it.
    """
    results = []
    # Find all '— reviewed by' positions
    pattern = re.compile(r'—\s*reviewed by\s*', re.IGNORECASE)
    
    for m in pattern.finditer(text):
        dash_end = m.end()
        # Extract Artist-Album-(Label) from text BEFORE the em-dash
        # Walk backwards from m.start() to find Artist – Album (Label)
        before = text[:m.start()]
        # The relevant artist-album section is the LAST "Artist – Album (Label)" before the dash
        # Use a forward search from the last paragraph break or from a safe point
        # Search backwards for a pattern: Artist – Album (Label)
        artist_album_match = None
        search_end = len(before)
        # Find all "Artist – Album (Label)" in before (from left to right)
        for am in re.finditer(r'(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)', before):
            artist_album_match = am  # keep updating to get the last one
        if not artist_album_match:
            continue
        artist = artist_album_match.group(1).strip()
        album  = artist_album_match.group(2).strip()
        label  = artist_album_match.group(3).strip()
        
        # Extract Reviewer+Date from text AFTER the em-dash
        after = text[dash_end:]
        # Format: "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II..."
        # Reviewer is everything before " of May"
        reviewer = re.sub(r'\s*of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}).*$', '', after, flags=re.IGNORECASE).strip()
        date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', after, re.IGNORECASE)
        date_str = date_m.group(1) if date_m else None
        
        print(f"  artist={artist!r}, album={album!r}, label={label!r}, reviewer={reviewer!r}, date={date_str!r}")
        results.append({'artist': artist, 'album': album, 'label': label,
                       'reviewer': reviewer, 'date': date_str})
    return results

print("=== Chain D.L.K. ===")
r = parse_chain_dlk(text1)
print(f"Found {len(r)} reviews")

# Free Jazz Collective  
text2 = html.unescape('A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

def parse_free_jazz(text):
    """
    Strategy: find each '. reviewed by', extract artist-album from text before it,
    and reviewer from text after.
    """
    results = []
    pattern = re.compile(r'\.\s*reviewed by\s*', re.IGNORECASE)
    
    for m in pattern.finditer(text):
        dot_end = m.end()  # position right after the period+space before "reviewed by"
        before = text[:m.start()]
        after  = text[dot_end:]
        
        # Extract artist-album from before
        # The relevant part is the LAST "Artist – Album (Label, Year)" before the period
        artist_album_match = None
        for am in re.finditer(r'(.+?)\s*[–—]\s*(.+?)\s*\(([^)]+)\)\s*$', before):
            artist_album_match = am
        if not artist_album_match:
            continue
        artist_full = artist_album_match.group(1).strip()
        album       = artist_album_match.group(2).strip()
        label_year  = artist_album_match.group(3).strip()
        # Strip trailing parentheticals from artist
        artist = re.sub(r'\s*\([^)]*\)\s*$', '', artist_full).strip()
        
        # Extract reviewer: everything before the first period in after
        reviewer = re.sub(r'\..*$', '', after).strip()
        
        print(f"  artist={artist!r}, album={album!r}, label={label_year!r}, reviewer={reviewer!r}")
        results.append({'artist': artist, 'album': album, 'label': label_year,
                       'reviewer': reviewer})
    return results

print("\n=== Free Jazz Collective ===")
r2 = parse_free_jazz(text2)
print(f"Found {len(r2)} reviews")
