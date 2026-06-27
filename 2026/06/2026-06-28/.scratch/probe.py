#!/usr/bin/env python3
import json, urllib.request, os
TABID = "6cd44534-9030-4f8f-902d-59f846e65ec2"
KEY = os.environ["CAMOFOX_API_KEY"]
exp = 'document.title + "|" + document.querySelectorAll(".listing2__product").length + "|" + document.querySelectorAll(".date-header").length'
data = json.dumps({"userId":"swarm_boomkat_2026_06_28","sessionKey":"boomkat","expression":exp}).encode()
req = urllib.request.Request(f"http://localhost:9377/tabs/{TABID}/evaluate", data=data, headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}"}, method="POST")
print(json.loads(urllib.request.urlopen(req).read()))