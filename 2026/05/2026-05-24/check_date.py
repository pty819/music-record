from datetime import datetime, timedelta
now = datetime.utcnow()
cutoff = (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)).date()
print(f"today: {now.date()}")
print(f"cutoff (3 days ago): {cutoff}")
print(f"is May 19 before cutoff May 21? {(datetime(2026,5,19) < datetime(cutoff.year, cutoff.month, cutoff.day))}")