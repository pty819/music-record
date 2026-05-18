#!/bin/bash
curl -s -L --max-time 30 \
  -H "User-Agent: Mozilla/5.0" \
  -H "Cookie: CookieConsent=1" \
  "https://www.thewire.co.uk/rss" \
  -o /home/liyifan/music-record/2026/05/2026-05-18/rss_output.xml
echo "Exit: $?"