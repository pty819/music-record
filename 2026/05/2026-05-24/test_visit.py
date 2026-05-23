#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/liyifan/music-record')
from scrape_jazztimes import visit_article

url = 'https://www.jazztimes.com/reviews/live/tyshawn-sorey-piano-concerto-for-marilyn-crispell-featuring-aaron-diehl-has-its-philly-hosted-world-premiere/'
print(f"Testing: {url}")
result = visit_article(url)
print("Result:", result)