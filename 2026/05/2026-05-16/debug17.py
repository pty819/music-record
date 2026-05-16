import re, html

text = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Simple test: match just Artist – Album (Label) before em-dash
# Pattern: text – text (text) — something
pat = re.compile(
    r'(.+?)\s*–\s*(.+?)\s*\(([^)]+)\)\s*—',
    re.IGNORECASE
)

for m in pat.finditer(text):
    print(f"Groups: {m.groups()}")
    print(f"Matched: {m.group()!r}")
    print(f"Start: {m.start()}, End: {m.end()}")
    print()
