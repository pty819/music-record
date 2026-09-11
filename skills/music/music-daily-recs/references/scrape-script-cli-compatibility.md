# Scrape 脚本 CLI 兼容性要求

scrape_html_parallel.py 统一调用格式：

```bash
timeout <N> python3 scrape_<site>.py --days 1.5
```

stdout 模式的脚本必须：
1. **接受 `--days` 参数**（float，默认 1.5，表示 cutoff 天数）
2. **将 JSON 结果 print 到 stdout**（`print(json.dumps(result, ...))`）
3. stderr 用于日志输出（parallel scraper 设 `stderr=DEVNULL`）

## 已知不兼容的历史写法

| 脚本 | 原始参数 | 修复方式 |
|---|---|---|
| hear65 | `--hours` | 加 `--days`，`hours = days * 24 if days else hours` |
| roots_world | `--ref-date`, `--max-pages` | 加 `--days`，传给 `scrape(days=...)` |
| world_music_central | `--hours`, `--date`, `--out` | 加 `--days`，cutoff 优先用 days |
| truth_and_lies_music | 只写文件不 print | 加 `print(json.dumps(result))` |

## 新脚本上线检查清单

```bash
# 1. 接受 --days
python3 bin/scrape_new_site.py --days 1.5 2>/dev/null; echo $?
# 期望: 0

# 2. 输出到 stdout
python3 bin/scrape_new_site.py --days 1.5 > /tmp/test.json 2>/dev/null
python3 -c "import json; d=json.load(open('/tmp/test.json')); print(f'items={len(d[\"items\"])}')"
# 期望: items=N (不是 ERR)

# 3. 并行测试
python3 bin/scrape_html_parallel.py --out-dir /tmp/parallel-test --days 1.5 --timeout 180
# 检查 new_site: ok items=N
```

## wild_city 特殊情况

wild_city 依赖 Camoufox REST API (`http://127.0.0.1:9377`)，不属于 HTML 层。
目前仍在 scrape_html_parallel.py 的 SCRIPTS 列表中（待移至 Camoufox 组）。
