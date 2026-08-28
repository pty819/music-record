#!/usr/bin/env python3
"""Step 2 verification for the merge gate: scraped_raw.json must be non-empty
and the first items must carry a site_id field."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "scraped_raw.json"
d = json.load(open(path))
items = d.get("items", []) if isinstance(d, dict) else d
assert len(items) > 0, "合并结果为空"
for i in items[:3]:
    assert "site_id" in i, f'缺少 site_id 字段: {str(i.get("album", "?"))[:30]}'
print(f"✅ {len(items)} 条数据，质量检查通过")
