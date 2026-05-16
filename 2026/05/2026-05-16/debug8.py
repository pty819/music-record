import re, html

REVIEW_PAT1 = re.compile(
    r"([A-Z][a-z]+ \d{1,2}, \d{4})"
    r"\s*[—–-]\s*"
    r"([^,]+)\s*,\s*"
    r"[\"\u201c\u201d\u2018\u2019]([^\"\u201c\u201d\u2018\u2019]+)[\"\u201c\u201d\u2018\u2019]"
    r"\s*\(([^)]+)\)"
    r"(?:\s*reviewed by ([^.]+))?",
    re.IGNORECASE
)

# Chain D.L.K.
text1 = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

print("=== Chain D.L.K. PAT1 matches ===")
for m in REVIEW_PAT1.finditer(text1):
    print("  Match:", m.groups())

# Free Jazz Collective
text2 = html.unescape('A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

print("\n=== Free Jazz Collective PAT1 matches ===")
for m in REVIEW_PAT1.finditer(text2):
    print("  Match:", m.groups())
