import re, html

text = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Pattern: Artist – Album (Label) — reviewed by Reviewer of Date
# Uses explicit Unicode codepoints:
#   en-dash  = \u2013 (between artist and album)
#   em-dash  = \u2014 (before "reviewed by")
pat = re.compile(
    r'([^\u2014]{1,60}?)\s*\u2013\s*'   # Artist – (en-dash)
    r'(.{1,80}?)\s*\(([^)]{2,100})\)\s*'  # Album (Label)
    r'\u2014\s*reviewed by\s*'              # em-dash — reviewed by
    r'([^o]{1,40}?)(?:\s*of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}))?$',
    re.IGNORECASE
)

for m in pat.finditer(text):
    artist, album, label, reviewer, date = m.groups()
    print(f"artist={artist.strip()!r}")
    print(f"album={album.strip()!r}")
    print(f"label={label.strip()!r}")
    print(f"reviewer={reviewer.strip()!r}")
    print(f"date={date!r}")
    print()
