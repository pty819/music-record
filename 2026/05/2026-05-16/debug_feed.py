import feedparser

feed = feedparser.parse("https://icareifyoulisten.com/feed")
entry = feed.entries[0]

sd = entry.get("summary_detail", {})
print("Type of summary_detail:", type(sd))
print("Keys:", sd.keys() if hasattr(sd, "keys") else "N/A")
val = sd.get("value", "")
print("Value length:", len(val))
print("Value first 500 chars:", repr(val[:500]))

print()
print("--- summary ---")
summ = entry.get("summary", "")
print("Summary length:", len(summ))
print("Summary first 500 chars:", repr(summ[:500]))

print()
print("--- raw content from description tag ---")
desc = getattr(entry, "description", "")
print("Description first 500:", repr(desc[:500]))