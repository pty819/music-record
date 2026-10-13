# 2026-07-08 Execution Notes

Cron session 实际跑通时的数据快照，用于交叉对照审计。

## 预检
- DB integrity: ok
- hermes-gateway: active
- VPN (bandcamp.com/feed): 200
- hermes-camoufox: active

## Step 1 — git pull
**失败**：`Connection closed by 28.0.0.60 port 22` (github.com DNS 投毒)
**处理**：跳过；按 pitfall 继续 Step 2-5。

## Step 2 — RSS（50 站 → 119 条）
需要切后台跑：前台 `terminal(timeout=900)` 被环境硬上限 600s 拒绝。
切到 `background=true` + `notify_on_complete=true` 后 60-80s 完成。

活跃产出排行（按条数）：
- hiroyasu_tangerine 16, cinra 13, avant_music_news 12, progarchives 12, side_line 12, fluid_radio 10
- bandcamp_daily 7, artscape 6, the_quietus 5, jazz_journal 3, post_punk_com 3
- （fluid_radio 是历史存档，预期 0 新但灌入 2013-2022 → 期望 0 是错的，实际会得到一批）
- the_wire 这次居然出 2 条（历史上 RSS 持续超时，mark 为 unreliable）

## Step 3 — HTML（18 脚本 → 54 条，5 errors）
并行完成 53s。
失败脚本：
- `free_jazz_blog`: urllib 失败 → rc=1
- `musique_machine`: HTTP 403
- `mixmag_asia`: HTTP 403
- `all_about_jazz`: HTTP 500
- `truth_and_lies_music`: HTTP 500

产出排行：
- roots_world 30, mikiki 15, bandwagon_asia 5, jazz_trail 2, dark_entries_be 2
- 其余 0 条（squids_ear 这次也是 0 — 可疑，前几天极高产）

## Step 4 — merge
dedup 移除 3 重复 → 170 条 scraped_raw.json。
`merged_from`: {rss_merged.json: 119, html_reviews.json: 54}

## Step 5 — Kanban Swarm
- Root: t_09433d6b
- Verifier: t_95f5f4f5
- Synthesizer: t_6fd8cdbc
- Idempotency: music-recs-swarm-2026-07-08
- 6 Camoufox workers 已创建

## 已知风险
- git pull 失败意味着 synthesizer 步的 `git push` 也可能失败（DNS 投毒未恢复）
- 如需紧急提交：网络恢复后手动跑 `cd ~/music-record && git push origin main`
- all_about_jazz / musique_machine / mixmag_asia / truth_and_lies_music 连续 403/500，
  应考虑升级到 Camoufox 层或加反爬头（pitfall 表已记录）
