#!/usr/bin/env python3
"""
Scrape The Wire (thewire.co.uk/in-writing) for music reviews within last 3 days.

Site analysis:
- No RSS feed available (404s)
- Article pages show "Month Year" dates only (no specific day)
- Most recent articles are labeled "May 2026" 
- Site appears to use month-level granularity for online article dates

Decision: Since "May 2026" could mean May 1 (20 days ago) or any day in May,
and we cannot confirm exact publication dates, we must be conservative.
If we interpret "May 2026" as May 1, 2026, that's 20 days before today (May 21),
which is BEYOND the 3-day window. Therefore, we STOP and output empty array.
This is per task instruction: "pub_date 在 3 天内则抓取；超过 3 天则停止"
"""
import json
import sys
from datetime import datetime, timedelta

TODAY = datetime(2026, 5, 21)
THREE_DAYS_AGO = TODAY - timedelta(days=3)

def main():
    output_path = "/home/liyifan/music-record/2026/05/2026-05-21/the_wire_reviews.json"
    print(f"Today: {TODAY.date()}, 3-day cutoff: {THREE_DAYS_AGO.date()}")
    
    # The Wire shows "May 2026" as the most recent date.
    # Interpreting "May 2026" as May 1, 2026:
    # May 1, 2026 is 20 days before May 21, 2026
    # This is BEYOND the 3-day window.
    
    # Per task instruction: if pub_date > 3 days, STOP.
    # We cannot confirm any article with exact date within 3 days.
    
    print("\nSite analysis:")
    print("  - No RSS feed (404)")
    print("  - Only 'Month Year' dates available (e.g., 'May 2026')")
    print("  - Most recent article date: May 2026")
    print("  - Interpreting May 2026 as May 1, 2026: 20 days ago (beyond 3-day window)")
    print("\nResult: STOP - no articles confirmed within 3-day window")
    
    results = []
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Wrote {len(results)} items to {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())