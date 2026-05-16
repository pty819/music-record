import re, html

text = html.unescape('微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# PAT3: artist [–—] album (label) — ... of date
pat3 = re.compile(
    r"([^\u2014–—]+)\s*[–—]\s*([^\(]+)\s*\(([^)]+)\)\s*—.*?(?:of\s+([A-Z][a-z]+ \d{1,2}, \d{4}))?",
    re.IGNORECASE
)

# PAT4: Free Jazz Collective
pat4 = re.compile(
    r"([^\u8211\u2014–—]+)\s*[–—]\s*([^\(]+)\s*\(([^)]+)\)\s*reviewed by\s+([^.]+)",
    re.IGNORECASE
)

for m in pat3.finditer(text):
    print("PAT3:", m.groups())

for m in pat4.finditer(text):
    print("PAT4:", m.groups())
