# 2026-06-09 Skill drift audit（文档 vs 运行态对账）

> 与 `2026-06-08-skill-refactor-overanalysis.md` 是同源教训的**合规版本**：
> 那次是"读代码推测 → 编 bug 故事"，这次是"先 probe → 报数字 → 等用户拍板"。

## 触发

用户问："音乐探索的那个 skill，我们目前最新的，总共获得数据源都是怎么获得的。"

注意问法是**"目前最新的"**——隐含要求 = 文档里写的 = 运行态实际跑的。我没假设 skill 是"对的"，直接 probe。

## 30 秒 probe → 4 行 drift 矩阵

跑了 3 个一次性的 probe 命令（**不**重构 skill / **不**改 sites.json）：

```bash
# 1. sites.json 真实分类
python3 /tmp/inspect_sites3.py
# → 51 站: 20 纯 RSS + 8 双标 (has_rss+playwright) + 13 纯 Camoufox + 3 skip + 7 跨抓冗余

# 2. bin/ 实际脚本
ls /home/liyifan/music-record/bin/scrape_*.py
# → 20 个（skill 文档只列 12 个）

# 3. cron 实际 job
hermes cron list
# → ec5ea562d589 (active), 6-9 04:00 触发
# skill 文档写的 6fd93b4a4c4c 根本不存在
```

## 4 处 drift 的逐条证据

### Drift 1：cron job ID

```
skill 写:  6fd93b4a4c4c（trigger_condition 段, "何时执行" 段, 文件路径表 4 处）
实际:    ec5ea562d589（hermes cron list 唯一活跃 job, next run 2026-06-09T04:00:00+08:00）

影响: 用户按文档跑 `hermes cronjob run 6fd93b4a4c4c` → 失败（且命令名是 cron 不是 cronjob）
```

### Drift 2：站点数口径

```
skill 写:  "27 个 RSS + 21 个 Camoufox" = 48
sites.json 实际:
  has_rss=True:          28 站
  crawl_strategy=playwright_headless: 21 站
  crawl_strategy=skip:    3 站
  交集 (has_rss AND playwright): 8 站 ← 双标, RSS 没用上
  总数:                  51 站

正确表述: 20 纯 RSS + 21 playwright (其中 8 站双标) + 13 纯 Camoufox + 3 skip = 51
```

### Drift 3：scrape 脚本数

```
skill 写: 12 个（"适用脚本列表"）
bin/ 实际: 20 个

skill 没列的 8 个增量:
  bandwagon_asia          (6-7 跑: 0 条)
  boomkat                 (6-7 跑: 100 条 ← 全场冠军)
  boomkat_bodies          (备援, 实测未用)
  hear65                  (6-7 跑: 0 条)
  roots_world             (6-7 跑: 22 条)
  sea_of_tranquility_v2   (备援, 实测 sea_of_tranquility 0 条)
  truth_and_lies_music    (6-7 跑: 0 条)
  world_music_central     (6-7 跑: 4 条, 同时是 playwright 标 → 跨抓冗余)
```

### Drift 4：7 站 "Camoufox→RSS 升级" 是真 bug

```
skill 写: "以下 7 个 Camoufox 站转 RSS（已验证可用）..." + 表格
sites.json 实际: 8 站 has_rss=True 但 crawl_strategy 仍是 playwright_headless

8 站: the_quietus / a_closer_listen / avant_music_news / icareifyoulisten
     / jazztimes / sequenza21 / rhythm_passport / attn_magazine

后果: kanban-swarm.py 过滤 `crawl_strategy == playwright_headless` 时**不**排除 has_rss=True
      → 仍派 20 个 Camoufox worker, RSS 100% 没被 fast-rss-scrape.py 覆盖
      → 这 8 站每条都要过一遍 5-15 分钟浏览器抓
```

## 工具 quirks（本次新发现）

- `hermes cron list` ✓，`hermes cronjob list` ✗（命令名是 `cron` 不是 `cronjob`）
- skill 文档里多处误写 `hermes cronjob`，需统一改
- `hermes cron show <id>` ✗（子命令是 `status` 不是 `show`）

## 报告给用户后用户没拍板

报告末尾给 4 个选项 + "都不动，等你拍板"：
1. 修双标站 8 站的 crawl_strategy
2. 修 skill 文档（cron ID / 站点数 / 脚本列表）
3. 修 free_jazz_blog.py JSON 输出 bug
4. 都不动

用户**没回**（session 结束）。下次接着这个 skill 时：
- 优先重跑 `audit-skill-drift.py` 看 drift 是否被修
- 如果 4 项全在 → 等用户拍板再做
- 如果用户已修 → 把对应 drift 行从 SKILL.md 删掉

## 自我评估（vs 2026-06-08 案例）

| 维度 | 06-08 失败 | 06-09 这次 |
|------|-----------|-----------|
| probe vs 推测 | 读 `kanban-batch-scrape.py` 推断 | 真跑 `inspect_sites3.py` + `hermes cron list` |
| 越权验证 | 跑 `--days 3` 越权加宽窗口 | 没改任何 config / 跑任何 scrape |
| bug 故事 | 编"重复抓 10 站"虚构症状 | 只列"SKILL.md 写 X / 实际 Y"事实 |
| 报告形式 | 改 SKILL.md 注入推测数据 | 报告里问"需要我接下来做什么"等拍板 |
| 跑产物 | 写错窗口的 1 条数据 | 6-7 实际跑出 243 条**已被 cron 产出**（不是我自己跑的）|

**核心差异**：这次 probe-then-report，没有 patch-then-claim。**符合"先验证再写"原则**。
