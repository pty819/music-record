import re, html

text = 'A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) – Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.'

print("Char at 96:", repr(text[96]))
print("Char at 97:", repr(text[97]))
print("Char at 98:", repr(text[98]))
print("Char at 99:", repr(text[99]))
print("Char at 100:", repr(text[100]))
print()
print("text[95:102]:", repr(text[95:102]))
print()
print("'). ' in text:", "'). ' in text")
print("'). ' in text:", "). " in text)
print("Period at:", [i for i, c in enumerate(text) if c == '.'])
print()
# Try splitting on "'). " - the closing paren after year followed by space
segments = text.split('). ')
print(f"Split on '). ': {len(segments)} parts")
for i, s in enumerate(segments[:3]):
    print(f"  [{i}]: {s[:80]!r}")
