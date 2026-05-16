import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Free Jazz Collective
text2 = html.unescape('A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')


def parse_chain_dlk(text):
    """
    Chain D.L.K. format: Artist – Album (Label) — reviewed by Reviewer of Date Artist – Album ...
    Strategy: find all ' — reviewed by' positions.
    For each, look BACKWARD for 'Artist – Album (Label)' pattern,
    and look FORWARD for 'Reviewer of Date' and 'Artist – Album' for next entry.
    """
    results = []
    # Find all em-dash positions followed by ' reviewed by'
    dash_pattern = re.compile(r'\u2014\s*reviewed by\s*', re.IGNORECASE)
    
    for m in dash_pattern.finditer(text):
        dash_start = m.start()
        dash_end   = m.end()
        
        # Artist-Album-Label: search BACKWARD from dash_start for 'Artist – Album (Label)'
        before = text[:dash_start]
        # Find all Artist – Album (Label) in 'before', take the LAST one
        artist_album_m = None
        for am in re.finditer(r'(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)', before):
            artist_album_m = am  # keep updating to get the last
        if not artist_album_m:
            continue
        artist = artist_album_m.group(1).strip()
        album  = artist_album_m.group(2).strip()
        label  = artist_album_m.group(3).strip()
        
        # After the em-dash: 'Reviewer of Date Artist_next – Album_next (Label_next)'
        after = text[dash_end:]
        
        # Reviewer: everything before ' of ' (in 'Reviewer of Date')
        # Split on ' of ' to get reviewer name
        of_match = re.search(r'\s+of\s+', after, re.IGNORECASE)
        if of_match:
            reviewer = after[:of_match.start()].strip()
        else:
            reviewer = re.sub(r'\s*—.*$', '', after).strip()
        
        # Date: 'of May 12, 2026' or 'of May 11, 2026'
        date_m = re.search(r'of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})', after, re.IGNORECASE)
        date_str = date_m.group(1) if date_m else None
        
        # Artist_next: everything AFTER 'of Date ' (which is 'Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by...')
        if date_m and date_str:
            remainder = after[date_m.end():].strip()
        else:
            remainder = after
        
        results.append({
            'artist': artist,
            'album': album,
            'label': label,
            'reviewer': reviewer,
            'date': date_str,
            'remainder': remainder[:60]
        })
    
    return results


def parse_free_jazz(text):
    """
    Free Jazz Collective: 'Artist – Album (Label) reviewed by Reviewer. Artist – Album (Label) reviewed by...'
    Also has: 'Artist (extra) – Album (Label) reviewed by Reviewer.'
    Strategy: find all '. reviewed by' positions.
    """
    results = []
    rev_pattern = re.compile(r'\.\s*reviewed by\s*', re.IGNORECASE)
    
    for m in rev_pattern.finditer(text):
        dot_start = m.start()
        after_dot = text[:dot_start].strip()
        
        # Artist-Album-Label: last 'Artist – Album (Label)' before the period
        artist_album_m = None
        for am in re.finditer(r'(.+?)\s*[–—]\s*(.+?)\s*\(([^)]+)\)\s*$', after_dot):
            artist_album_m = am
        if not artist_album_m:
            continue
        
        artist_full = artist_album_m.group(1).strip()
        album       = artist_album_m.group(2).strip()
        label_year  = artist_album_m.group(3).strip()
        
        # Strip trailing parens from artist
        artist = re.sub(r'\s*\([^)]*\)\s*$', '', artist_full).strip()
        
        # Reviewer: text AFTER 'reviewed by', up to next period
        after_rev = text[m.end():].strip()
        reviewer = re.sub(r'\..*$', '', after_rev).strip()
        
        results.append({
            'artist': artist,
            'album': album,
            'label': label_year,
            'reviewer': reviewer
        })
    
    return results


print("=== Chain D.L.K. ===")
chain_results = parse_chain_dlk(text1)
for r in chain_results:
    print(f"  {r['artist']} – {r['album']} [{r['label']}] by {r['reviewer']} ({r['date']})")
    print(f"    remainder: {r['remainder']}")

print("\n=== Free Jazz Collective ===")
fj_results = parse_free_jazz(text2)
for r in fj_results:
    print(f"  {r['artist']} – {r['album']} [{r['label']}] by {r['reviewer']}")
