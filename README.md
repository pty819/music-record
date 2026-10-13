# 音乐推荐 / Music Record

每日音乐推荐清单，聚焦前卫/实验/学院派爵士/电子/世界音乐。

## 目录结构

```
{YYYY}/
└── {MM}/
    └── {YYYY-MM-DD}.md   # 当日推荐清单
skill/
└── avant-garde-daily-recs.md   # 采集 skill 文档
    └── references/
        ├── sites.json    # 站点配置
        └── quick-ref.md  # 快速参考
```

## 推荐标准

所有评分 >= 6 的候选专辑全部收录，无数量上限：
- **主推荐**：总分 >= 9
- **候选补充**：总分 6-8
- **全文未获取**：paywall 站且跨站搜索无实质结果
- **搜索补充**：paywall/cloudflare 站，跨站搜索后补充了信息

数据来源：RSS 优先，Playwright 保底，web_search 跨站补充。

## 更新

每日北京时间凌晨 03:00 自动更新。
