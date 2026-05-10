# Batch Concurrency Pattern — Kanban Fan-Out

> **Canonical reference**: `devops/kanban-orchestrator/references/batch-concurrency-pattern.md`
> This file exists here because `music-daily-recs` is the primary caller and needs a local pointer.

## TL;DR

- **Batch size = 2**（不是 43 并发）
- 43 个 scraper 任务分 22 批跑完
- 每批 `parents=[上一批所有 task_id]`，下一批等上一批全部 `done` 才解锁
- Aggregator 的 `parents=all_task_ids`，等全部 43 个 scraper done 才执行

## 脚本位置

```bash
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py          # dry run
python3 /home/liyifan/.local/bin/kanban-batch-scrape.py --confirm # 创建任务
```

## 关键坑

1. **scraper profile 必须有独立 .env + config.yaml**，否则 401 崩溃
2. **所有 scraper workspace 统一为 `dir:~/music-record/2026/MM`**，不用 `scratch`！scraper 各写各的 `{site_id}_reviews.json`，aggregator 读目录里所有 `*_reviews.json`，scratch 目录互相不可见
3. **batch script 已硬编码 output 路径**：所有 scraper JSON + 最终 markdown 直接写入 `~/music-record/2026/MM/`，无需额外 copy 步骤
