text = 'A roundup of reviews and features published at The Free Jazz Collective over the last several days. Goal Weight (Maggie Cox and Jennifer Gersten) \u2013 Keep Telling Yourself That (Relative Pitch, 2026) reviewed by Hrayr Attarian. Anthony Braxton \u2013 2 Comp (2023) (Schott Music, 2025) reviewed by Don Phipps.'

idx = text.find('reviewed by')
print('reviewed by at:', idx)
print('Before 20:', repr(text[idx-20:idx]))
print('After:', repr(text[idx:idx+30]))
print()
print('Char before reviewed:', repr(text[idx-1]))
print('Chars -5 to -1:', repr(text[idx-5:idx]))
