# 部署模型与文件组织（2026-06-11 重构）

## 最终结构

```
~/music-record/                          ← 唯一源仓库（git push 这里）
├── bin/ (33 scripts)                    ← 所有运行脚本
├── data/sites.json                      ← 唯一站点配置
├── 2026/MM/DD/                          ← 运行产物
└── skills/music/music-daily-recs/
    └── SKILL.md                         ← 技能文档（git 管理）

~/.hermes/skills/music/music-daily-recs/  ← Hermes skill 目录
├── SKILL.md                             ← 真实文件（从 git cp 过来）
├── scripts/ → ~/music-record/bin/       ← symlink
└── references/                          ← 调试文档
```

## 关键规则

1. **所有代码修改在 `~/music-record/` 里做**，commit + push GitHub
2. **SKILL.md 改完后手动 cp**：`cp skills/music/music-daily-recs/SKILL.md ~/.hermes/skills/music/music-daily-recs/`
3. **不要往 `~/.local/bin/` 复制任何东西** — 那是旧的部署方式
4. **不要复制 `sites.json` 到别的位置** — 历史上 `~/.minimax/music-sites/sites.json` 导致过严重的不同步问题

## 已删除的历史遗留

- `~/.local/bin/scrape_*.py`（26 个重复副本）— 2026-06-11 删除
- `~/.minimax/music-sites/`（14MB，含旧 sites.json + 50+ 旧输出）— 2026-06-11 删除
- `~/.hermes/skills/.../scripts/` 下的独立文件副本 — 改为 symlink

## 脚本路径解析约定

所有脚本通过以下方式定位 `data/sites.json`：
```python
from pathlib import Path
SITES_JSON = Path(__file__).resolve().parent.parent / "data" / "sites.json"
```

这样无论从哪个目录调用脚本（cron、kanban worker、手动），都能正确找到配置。
