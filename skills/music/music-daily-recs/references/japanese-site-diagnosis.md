# 日本站点诊断方法论

## 2026-06-13: 为什么日本推荐质量不行

### 问题
用户反馈"日本有很多地下乐队但推荐里没看到"。调查发现 12 个日本站点中只有 5 个出数据，且大部分不是地下音乐。

### 诊断步骤（可复用于任何"某地区/类型推荐不行"的场景）

#### Step 1: 统计当日各站点产出
```bash
cd /home/liyifan/music-record/2026/06/$(date +%Y-%m-%d)
python3 -c "
import json, os
for f in sorted(os.listdir('.')):
    if f.endswith('.json'):
        with open(f) as fh:
            data = json.load(fh)
        items = data.get('items', data.get('reviews', [])) if isinstance(data, dict) else data
        print(f'{f}: {len(items)} items')
"
```

#### Step 2: 分类目标地区的站点
```bash
cd /home/liyifan/music-record && python3 -c "
import json
with open('data/sites.json') as f:
    data = json.load(f)
sites = data.get('sites', data) if isinstance(data, dict) else data
# 根据地区替换关键词
jp_kw = ['japan', 'tokyo', 'mikiki', 'jazztokyo', 'サナコレ', 'musicircus',
         'suigyu', 'cinra', 'arban', 'ontomo', 'artscape', 'hosoda', 'hiroyasu', 'jazzbrat']
for s in sites:
    text = str(s).lower()
    if any(k in text for k in jp_kw):
        sid = s.get('id', '')
        has_rss = s.get('has_rss', False)
        path = 'RSS' if has_rss else ('HTML' if sid in HTML_SCRIPT_IDS else 'Camoufox')
        print(f'{s.get(\"name\",\"?\"):30s} path={path:10s}')
"
```

#### Step 3: 验证 scraper 是否能独立运行
对每个 0 项的站点，直接跑 scraper 确认是 scraper 问题还是站点问题：
```bash
python3 bin/scrape_<site_id>.py --days 1 2>/dev/null | python3 -c "
import json, sys
raw = sys.stdin.read()
lines = raw.strip().split('\n')
json_str = '\n'.join(l for l in lines if not l.startswith('Done:'))
data = json.loads(json_str)
print(f'{len(data.get(\"items\",[]))} items')
"
```

#### Step 4: 检查站点是否已死
```bash
# RSS 站：检查 feed 是否返回内容
curl -sL -m 15 -A "Mozilla/5.0" "<rss_url>" | wc -c
# 0 字节 = feed 已死

# Camoufox 站：检查 DNS 和可达性
dig +short <domain>
# 28.0.0.x = DoD 保留地址，站点已死
```

#### Step 5: 检查流水线接线完整性
```bash
# 确认 HTML 站点在两个地方都注册了
grep -c <site_id> bin/kanban-swarm.py    # HTML_SCRIPT_IDS
grep -c <site_id> bin/scrape_html_parallel.py  # SCRIPTS
# 两个都应该是 1
```

### 本次发现的死站

| 站点 | 死因 | 证据 |
|---|---|---|
| 水牛 Suigyu | RSS feed 返回 0 字节 | `curl -sL https://suigyu.com/feed/ \| wc -c` → 0 |
| 岡島豊樹 jazzbrat | 最后一篇 2024-09 | RSS 有内容但全是旧的 |
| サナコレ | DNS 解析到 28.0.0.199 (DoD 保留) | `dig +short mochizukisana.com` → 28.0.0.199 |

### 本次发现的接线 bug

**Mikiki**：在 `kanban-swarm.py:HTML_SCRIPT_IDS` 注册了，但 `scrape_html_parallel.py:SCRIPTS` 里没有。手动跑 scraper 能出 12 条数据，但流水线里从没调用过。

### 站点分类洞察

日本"站点多"≠"地下音乐覆盖好"：
- cinra/artscape/ontomo 是文化杂志，音乐只是子类
- 偏愛的収集記 返回大量条目但全是西方经典再版（Sun Ra、Albert Ayler）
- 真正覆盖日本地下音乐的站（Mikiki、JazzTokyo）反而没出数据

### 新站点接入结果（2026-06-13）

以下 7 个站点已接入 sites.json + fast-rss-scrape.py TAG_MAP：

| 站点 | ID | RSS URL | 状态 |
|---|---|---|---|
| S (Varelser) | varelser | `https://note.com/varelser/rss` | ✅ 已接入 |
| Noise Not Music | noisenotmusic | `https://noisenotmusic.com/feed/` | ✅ 已接入 |
| aJazzNoise | ajazznoise | `https://ajazznoise.com/feed/` | ✅ 已接入 |
| kansai_studies | kansai_studies | `https://note.com/kansai_studies/rss` | ✅ 已接入 |
| prtcll (Leo Okagawa) | prtcll | `https://note.com/prtcll/rss` | ✅ 已接入 |
| 米教タルタル | komekyo510 | `https://note.com/komekyo510/rss` | ✅ 已接入 |
| Leap250's Blog | leap250 | `https://leap250.blog/feed/` | ✅ 已接入 |

验证：`timeout 60 python3 bin/fast-rss-scrape.py --days 30 --workers 8` → varelser 1条, noisenotmusic 4条, leap250 2条。

**不可接入的站点（留档）：**

| 站点 | 问题 |
|---|---|
| Kaala Music (kaalamusic.com) | Japan Underground Metal/Punk/Hardcore，无 RSS，需 Camoufox |
| AVYSS (avyss.net) | Quietus 推荐的日本先锋音乐网站，目前打不开 |
| Clear And Refreshing | Ian Martin 的日本地下音乐博客，2023年停更 |
| futureweeks (note.com) | 年终榜单型博客，非日常更新 |
