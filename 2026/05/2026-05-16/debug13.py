import re, html

text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Pattern: "Artist – Album (Label) — reviewed by Reviewer of Date"
# Captures: Artist, Album, Label, Reviewer, Date
CHAIN_DLK_PAT = re.compile(
    r'(.{1,50}?)\s*–\s*(.{1,80}?)\s*\(([^)]{2,100})\)\s*—\s*reviewed by\s*([^of]+?)\s*(?:of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}))?',
    re.IGNORECASE
)

for m in CHAIN_DLK_PAT.finditer(text1):
    artist, album, label, reviewer, date = m.groups()
    print(f"artist={artist.strip()!r}, album={album.strip()!r}, label={label.strip()!r}, reviewer={reviewer.strip()!r}, date={date!r}")
