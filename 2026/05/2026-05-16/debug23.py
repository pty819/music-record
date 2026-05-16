import re, html

text2 = html.unescape('A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) &#8211; Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton – 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.')

# Check what char separates '. reviewed by'
idx = text2.find('reviewed by')
print(f"'reviewed by' at: {idx}")
print(f"Before: {text2[idx-5:idx+20]!r}")
print(f"Before chars: {[hex(ord(c)) for c in text2[idx-5:idx]]}")

# What does the text look like around the separator?
for i in range(max(0,idx-10), idx+5):
    print(f"  [{i}] {text2[i]!r} = U+{ord(text2[i]):04X}")
