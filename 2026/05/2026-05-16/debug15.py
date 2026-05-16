import re, html

text = html.unescape('A roundup of reviews published at Chain D.L.K. over the last week. 微風ゾーン Bifuu_ZONE – The West (Constellation Tatsu) — reviewed by Vito Camarretta of May 12, 2026 Anton Toorell – Solos II (Thanatosis Produktion) — reviewed by Vito Camarretta of May 11, 2026')

# Print hex of first 200 chars
print("Hex:", text[:200].encode('unicode-escape').decode('ascii'))
print()
# Print all unique dash-like chars
for i, c in enumerate(text):
    if ord(c) > 127 and ord(c) < 8200:
        print(f"  char at {i}: {c!r} = U+{ord(c):04X}")
