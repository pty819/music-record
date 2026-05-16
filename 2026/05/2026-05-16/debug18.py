import re, html

text = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Strategy: split on " — reviewed by" 
# segments[0] = intro + first_artist_album (no reviewer yet)
# segments[1] = "Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis)"
# segments[2] = "Vito Camarretta of May 11, 2026"
# etc.
#
# For i=0: artist_album from segments[0], reviewer+date from segments[1] after extracting artist-album-2
# For i=1: artist_album from segments[1] after extracting it (since segments[1] contains artist-album-2 after date)
# Actually simpler: segments[i] has artist_album for entry i, and reviewer+date for entry i, 
#   plus artist_album for entry i+1

# Better approach: iterate through text using look-ahead for " — reviewed by"
# Find all artist-album patterns and match them with the next " — reviewed by"
# Pattern: Artist – Album (Label) — reviewed by Reviewer of Date
CHAIN_DLK_PAT = re.compile(
    r'(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*—\s*reviewed by\s*'
    r'([^oO]+?)(?:\s*[oO][fF]\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}))?',
    re.IGNORECASE
)

for m in CHAIN_DLK_PAT.finditer(text):
    artist, album, label, reviewer, date = m.groups()
    print(f"artist={artist.strip()!r}, album={album.strip()!r}, label={label.strip()!r}, reviewer={reviewer.strip()!r}, date={date!r}")
