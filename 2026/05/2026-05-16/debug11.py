import re, html

# Chain D.L.K.
text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Free Jazz Collective
text2 = html.unescape('A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

def parse_chain_dlk(text):
    """Split on ' — reviewed by' and pair artist with reviewer info."""
    # Split on ' — reviewed by' (case-insensitive)
    parts = re.split(r'\s*—\s*reviewed by\s*', text, flags=re.IGNORECASE)
    results = []
    # parts[0] = intro + last_artist_album (the artist-album BEFORE the first reviewer)
    # parts[1] = "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II..."
    # For i=1 onwards: parts[i] = "reviewer info" + "Artist – Album (Label)" + "— reviewed by..."
    for i in range(1, len(parts)):
        # Each part has: "Reviewer of Date Artist – Album (Label)"
        # We need the artist-album from parts[i-1] and reviewer+date from parts[i]
        # But parts[i-1] is the artist-album part BEFORE the em-dash
        # and parts[i] starts with "Reviewer of Date Artist – Album"
        prev_part = parts[i-1]
        curr_part = parts[i]
        
        # Extract artist-album from prev_part (it's after the last em-dash in prev_part)
        # Find the last em-dash in prev_part
        em_dash_pos = prev_part.rfind('—')
        if em_dash_pos == -1:
            # The first part has no em-dash; the artist-album is at the very end
            artist_album_section = prev_part.strip()
        else:
            artist_album_section = prev_part[em_dash_pos+1:].strip()
        
        # Now extract reviewer+date+next_artist from curr_part
        # Format: "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis)"
        # Split curr_part at the next em-dash or at " of " followed by date
        # Extract date first
        date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', curr_part)
        date_str = date_m.group(1) if date_m else None
        
        # Extract reviewer name (everything before " of ")
        reviewer = re.sub(r'\s*of\s+.*$', '', curr_part).strip()
        if not reviewer or len(reviewer) < 2:
            continue
        
        # Find artist-album: look for Artist – Album (Label) pattern in curr_part
        # after the reviewer+date
        remainder = curr_part
        if date_m:
            remainder = curr_part[date_m.end():].strip()
        
        # Look for "Artist – Album (Label)" pattern
        artist_m = re.match(r'^(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*$', remainder.strip())
        if not artist_m:
            continue
        artist, album, label = artist_m.groups()
        
        results.append({
            'artist': artist.strip(),
            'album': album.strip(),
            'label': label.strip(),
            'date': date_str,
            'reviewer': reviewer,
        })
        print(f"  CHAIN_DLK: {artist.strip()} – {album.strip()} [{date_str}] ({label.strip()}) by {reviewer}")
    
    return results

print("=== Chain D.L.K. ===")
parse_chain_dlk(text1)

def parse_free_jazz(text):
    """Split on '. reviewed by' and pair artist with reviewer."""
    # Split on '. reviewed by' (case-insensitive)
    parts = re.split(r'\.\s*reviewed by\s*', text, flags=re.IGNORECASE)
    results = []
    # parts[0] = intro + last_artist_album (before first '. reviewed by')
    # parts[1] = "Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps."
    for i in range(1, len(parts)):
        prev_part = parts[i-1]
        curr_part = parts[i]
        
        # Get artist-album from prev_part
        artist_m = re.match(r'^(.+?)\s*[–—]\s*(.+?)\s*\(([^)]+)\)\s*$', prev_part.strip())
        if not artist_m:
            # Try without parentheses
            artist_m = re.match(r'^(.+?)\s*[–—]\s*(.+?)\s*reviewed by', prev_part.strip(), re.IGNORECASE)
            if not artist_m:
                continue
            artist_full = artist_m.group(1).strip()
            album = artist_m.group(2).strip()
            label = ''
        else:
            artist_full, album, label = artist_m.groups()
            artist_full = artist_full.strip()
            album = album.strip()
            label = label.strip()
        
        # Strip trailing parentheticals from artist
        artist = re.sub(r'\s*\([^)]*\)\s*$', '', artist_full).strip()
        
        # Extract reviewer (everything before the first period in curr_part)
        reviewer = re.sub(r'\..*$', '', curr_part).strip()
        if not reviewer or len(reviewer) < 2:
            continue
        
        # Does curr_part have another entry?
        # Look for "Artist – Album" pattern in curr_part (after reviewer + period)
        remainder = re.sub(r'^[^.]+\.\s*', '', curr_part, count=1)
        next_m = re.match(r'^(.+?)\s*[–—]\s*(.+?)\s*\(([^)]+)\)\s*(?:reviewed by|$)', remainder.strip(), re.IGNORECASE)
        
        results.append({
            'artist': artist,
            'album': album,
            'label': label,
            'reviewer': reviewer,
        })
        print(f"  FREE_JAZZ: {artist} – {album} [{label}] by {reviewer}")
        
        if next_m:
            next_artist_full, next_album, next_label = next_m.groups()
            next_artist = re.sub(r'\s*\([^)]*\)\s*$', '', next_artist_full.strip()).strip()
            # Extract reviewer from curr_part after next entry
            next_rev_m = re.search(r'reviewed by\s+([^.]+)', curr_part, re.IGNORECASE)
            next_reviewer = next_rev_m.group(1).strip() if next_rev_m else ''
            results.append({
                'artist': next_artist,
                'album': next_album.strip(),
                'label': next_label.strip(),
                'reviewer': next_reviewer,
            })
            print(f"  FREE_JAZZ2: {next_artist} – {next_album.strip()} [{next_label.strip()}] by {next_reviewer}")
    
    return results

print("\n=== Free Jazz Collective ===")
parse_free_jazz(text2)
