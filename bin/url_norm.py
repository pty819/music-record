#!/usr/bin/env python3
"""url_norm.py — 条目身份键（07:00 增量评分用）。

normalize_url: scheme 统一（http/https 视为同一）、host 小写、去 www. 以外不动、
去掉末尾 /、丢弃 utm_* / fbclid / gclid 等追踪参数、去掉 #fragment。
item_key: 有 url 用规范化 url；没有 url 时退化为 site_id|artist|album。
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "yclid", "_hsenc", "_hsmi", "ref", "ref_src", "spm",
}


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path or ""
    while path.endswith("/"):
        path = path[:-1]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    query.sort()
    # scheme 统一成 https：http 与 https 视为同一条
    return urlunsplit(("https", host, path, urlencode(query), ""))


def item_key(item: dict) -> str:
    u = normalize_url(item.get("url") or "")
    if u:
        return u
    return "noid:" + "|".join(
        str(item.get(k) or "").strip().lower() for k in ("site_id", "artist", "album")
    )
