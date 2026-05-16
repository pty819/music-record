import re, html

text = 'A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) – Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.'

print("Looking for 'reviewed by':")
idx = text.find('reviewed by')
print(f"  at index {idx}")
print(f"  context: {text[max(0,idx-10):idx+30]!r}")

print("\nTrying pattern: r'\\.\\s*reviewed by'")
pat = re.compile(r'\.\s*reviewed by', re.IGNORECASE)
matches = list(pat.finditer(text))
print(f"  Matches: {matches}")

print("\nTrying literal match:")
print(f"  '). ' in text: {'). ' in text}")
print(f"  '. reviewed' in text: {'. reviewed' in text}")
print(f"  '. rev' in text: {'. rev' in text}")

# What does re.findall give for dots?
dots = [(m.start(), m.group()) for m in re.finditer(r'\.', text)]
print(f"\nAll period positions (first 10): {dots[:10]}")
