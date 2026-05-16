import re, html

text = html.unescape('Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

# PAT4: "Artist (extra) — Album (Label, Year) reviewed by Reviewer."
# artist: everything before the dash, strip trailing space
# album: between dash and (
# label_year: inside ()
pat4 = re.compile(
    r"([^\u8211\u2014–—]+?)\s*[–—]\s*([^\(]+?)\s*\(([^)]+)\)\s*reviewed by\s+([^.]+)",
    re.IGNORECASE
)

for m in pat4.finditer(text):
    print("PAT4:", m.groups())
