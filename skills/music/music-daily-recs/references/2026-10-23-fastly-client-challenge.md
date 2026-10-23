# Fastly「Client Challenge」把 feedparser 的请求挡在门外（2026-10-23）

## 现象

`bandcamp_daily` 连续 0 条（10-10 起每天都是 0），但站点本身正常更新：
`https://daily.bandcamp.com/feed` 明明有 38 条 item，其中 6 条在 36h 窗口内。

管道不报错、不告警——`fast-rss-scrape.py` 打印 `[bandcamp_daily] 0 条`，
看起来跟「月更站本周没发文」一模一样。**这正是它藏了 13 天的原因。**

## 根因：TLS ClientHello 指纹

Fastly 的 bot defense 按 TLS 握手指纹打分，命中就返回一个 **HTTP 200 的
「Client Challenge」页面**（`content-type: text/html`，3038 字节，标题
`Client Challenge`，带 `_fs_ch_st_*` cookie），而不是 feed。

feedparser 拿到 HTML 后解析失败 → 0 条 entry，**没有任何 HTTP 错误码**。

关键在于 urllib 默认 opener 与浏览器发的 ClientHello 不同：

- `http.client._create_https_context()` = `ssl.create_default_context()` **+ ALPN(http/1.1) + post_handshake_auth=True**
- `ssl.create_default_context()` 单独用 = **不带 ALPN、不带 PHA**

实测（6/6 次稳定复现）：

| 路径 | bandcamp_daily |
|---|---|
| `feedparser.parse(url)`（默认） | **0 条** |
| `feedparser.parse(url, handlers=[HTTPSHandler(context=ssl.create_default_context())])` | **38 条** |

排除掉的因素：User-Agent、Accept 头、Referer、Cookie 重试都**不是**原因——
换浏览器 UA 照样 0 条，带 cookie 重试 4 次照样是挑战页。
真正起作用的是**显式传入 `ssl.create_default_context()`**。

## 修法

`bin/fast-rss-scrape.py` 加 `_parse_feed()`，只在「bozo=True **且** 0 条 entry」
时用一个不带 ALPN 的 SSL context 重试一次：

```python
def _parse_feed(rss_url: str):
    feed = feedparser.parse(rss_url)
    if getattr(feed, "entries", None) or not getattr(feed, "bozo", False):
        return feed
    ctx = ssl.create_default_context()
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    retry = feedparser.parse(rss_url, handlers=handlers)
    return retry if getattr(retry, "entries", None) else feed
```

### 两个必须守住的约束

1. **别改 User-Agent。** 实测换浏览器 UA 会让 `avant_music_news` 从 20 条掉到 0 条
   （它对 UA 很敏感）。UA 保持 feedparser 默认值，只换 TLS context。
2. **只在 bozo=True 时重试。** 合法但没更新的 feed 是 `bozo=False`，
   若无条件重试，月更站（jazz_right_now / noise_receptor / fdu_de 等）
   常年 0 条，每个都要多打一次请求。

改完实测：60 站全跑，**只有 bandcamp_daily 从 0 → 6 条，其余站条数一字未变**。

## 另一个连带 bug：--if-needed 看不见 RSS 层的补抓

补抓后跑 `daily_pipeline.py --if-needed` 竟然是 no-op。原因是
`newest_reviews_mtime()` 只 glob `*_reviews.json`（HTML 层产物），
而 `merge_scraped.py` 的输入其实是 **rss_merged.json + *_reviews.json 两类**。
RSS 层补抓 → `rss_merged.json` 变新 → 但没人看它 → `stale_tail=False` → 不补货。

修法：把 `rss_merged.json` 一并纳入 mtime 取值。

```python
for p in list(date_dir.glob("*_reviews.json")) + [date_dir / "rss_merged.json"]:
```

修完后 `--if-needed` 正常识别尾巴：merge 196 条 → 6 条新 → 评分 → 报告 172 → 178 条 → push。

## 通用教训

**「某站 0 条」有三种完全不同的原因，别混为一谈：**

| 原因 | 怎么区分 | 该做什么 |
|---|---|---|
| 站点真没更新 | 抓得到 feed，但窗口内无 item（`bozo=False`） | 什么都不做，正常 |
| 抓到 feed 但**解析不出**（被 bot 墙挡了） | `bozo=True` + 0 entry + 响应是 HTML | 查 ClientHello 指纹 / User-Agent / 认证 |
| 月更站 | `bozo=False` + feed 内 item 都是旧日期 | 正常，用 `--days 60` 验证 |

**判据要落到「响应到底是什么」上，不能停在「0 条」。** 本例中管道每站都打印
`0 条`，日志上看不出任何异常——只能靠直接 `curl`/python 抓那个 feed 看响应
body 是不是 XML 才能发现。

## 排查用命令

```bash
# 看某个 feed 拿到的到底是什么（挑战页会是 <!DOCTYPE html> 而不是 <?xml）
.venv/bin/python -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
req = urllib.request.Request('https://daily.bandcamp.com/feed',
                             headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=25, context=ctx)
b = r.read()
print('CT:', r.headers.get('content-type'), 'len:', len(b))
print('XML' if b[:5] == b'<?xml' else 'BLOCKED')
print(b[:300])
"
```

**记住 `context=ctx` 是关键。** 不传 context（用 urllib 默认）会拿到挑战页，
传了就正常——这正是 bug 的隐蔽之处：同一个 URL，换个 TLS 参数结果完全相反。
