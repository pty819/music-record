# 2026-06-08 Sea of Tranquility 空结果卡死（代表性案例）

> Worker 反复重抓/重验证/重写爬虫 → 90 iteration 烧光 → failure_limit 触发 → swarm 依赖图判定 verifier/synthesizer 永远无法解锁 → 当天报告静默缺失。**这是 §4 #4 "全空结果"快速路径的触发案例**。

## 一句话根因

Sea of Tranquility 站点最新评论 2026-06-01（5 天前），36h 窗口内 0 条 review。但 worker 不肯接受"全空"结果，反复重新验证 → 写 99 条带 null pub_date 的脏数据 → 又重新写爬虫 → 触发 write_file 缩进 bug → 又继续 patch。两次 run 都烧光 90 iteration，failure_limit=2 触发 → worker blocked → swarm 依赖图判定 verifier/synthesizer 永远无法解锁 → 静默死亡。

## 时间线

| 时间 | 事件 | iter 消耗 |
|------|------|----------|
| 04:00 | cron 触发，Step 0-5 顺利完成（RSS 73 / HTML 18 / 合并 91 / 创建 20 Camoufox workers） | — |
| 04:10 | SOT worker 启动 | 0 |
| 04:10-04:25 | Run #1：探索 RSS / 找站点结构 / 写 243 行主脚本 / 跑（127.9s）→ 91 条 / 修补 2 个 NEW / 写 v2 跑 110s → 99 条 / 调试日期 regex / 反复 patch JSON | 90 |
| 04:25 | iter 耗尽，failure 1/2，dispatcher 立即 retry | — |
| 04:26-04:36 | Run #2（**全新 session**，不知道 Run 1 干过啥）：重新读 99 条 JSON / 列出 14 条日期 / **正确决策写 0 条 + complete**（行 2537）/ 自我反悔 / 重写爬虫 / 触发 write_file 缩进 bug / 反复 patch | 90 |
| 04:36 | iter 耗尽，failure 2/2，`gave_up`，标 `blocked` | — |
| 04:36+ | swarm 依赖图判定 verifier/synthesizer 永远无法解锁，**直接不创建** | — |
| 12:00+ | 用户问"我今天的推荐呢？"才被发现，8 小时静默死亡 | — |

## 4 个共性放大因子

| 因子 | 表现 | 跨站影响 |
|------|------|---------|
| A. write_file 缩进 strip | 函数内 4-space 缩进被吃掉 | 所有 worker |
| B. heredoc 触发审批 | `<<EOF` 触发人工审批 → [exit -1] | 所有 worker |
| C. agent 不知道前 run 干过啥 | 第二次 run 重新发现 99 条 JSON | 所有 retry |
| D. agent 不敢"接受 0 条" | 0 条结果触发完美主义 | 所有低频站 |

A/B 的修复见 §4 #6（worker body 内化）。
C 是设计权衡——swarm retry 全新 session，无跨 run memory。
D 的修复见 §4 #4（全空结果快速路径）。

## 关键 lesson

> **空结果是最高难度的边界 case**。有数据时 agent 满足于"我抓到了"；空结果时它无法满足于"我确认了"，会反复追求 100% 确定性。worker prompt 必须**显式禁止**"反复验证空结果"这种反模式——不能仅靠"信任 spec"暗示，必须在 body 顶部写明触发条件 + 1-2 步可执行代码。

## 完整日志

需要复现时通过 `hermes kanban log t_acbb9c5f` 重新拉取（3059 行原始 kanban log，crontab 启动时 `/tmp` 会清掉）。
