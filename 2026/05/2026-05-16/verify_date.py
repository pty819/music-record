
from datetime import datetime
today = datetime(2026, 5, 16)
d = datetime(2026, 5, 12)
print('May 12 age:', (today - d).days)
d2 = datetime(2026, 5, 13)
print('May 13 age:', (today - d2).days)
print('So May 12 is 4 days old - outside 3-day window')
