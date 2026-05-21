import json, os
import requests
import os

# 绝对路径
BASE_DIR = "/home/liyifan/music-record"
os.chdir(BASE_DIR)

# 加载环境变量MINIMAX_CN_API_KEY
MINIMAX_CN_API_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")
if not MINIMAX_CN_API_KEY:
    with open("/home/liyifan/.hermes/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "MINIMAX_CN_API_KEY" in line:
                MINIMAX_CN_API_KEY = line.split("=", 1)[1].strip().strip("'\"").strip()

LLM_API_URL = "https://api.minimaxi.com/v1/chat/completions"
LLM_MODEL = "MiniMax-M2.7"

today = "2026-05-18"
date_dir = f"2026/05/{today}"
full_date_dir = os.path.join(BASE_DIR, date_dir)

# 读取现有markdown和filtered.json
with open(os.path.join(BASE_DIR, f"recommend/{today}.md"), "r") as f:
    lines = f.read().splitlines()

with open(os.path.join(full_date_dir, "filtered.json"), "r") as f:
    passed = json.load(f)

# 分级：只处理low
low = [r for r in passed if 6 <= r["total_score"] < 7]

# LLM总结函数
def summarize_cn(artist, album, excerpt, tags=""):
    prompt = f"""你是一位专业华语乐评人。用1-2句简洁的中文总结这张专辑的核心特点：艺人是谁、什么声音风格、最亮眼之处。不要空话套话。

艺人：{artist}
专辑：{album}
摘要：{excerpt[:1000]}
标签：{tags}
"""
    headers = {
        "Authorization": f"Bearer {MINIMAX_CN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    try:
        resp = requests.post(LLM_API_URL, headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        summary = result["choices"][0]["message"]["content"].strip()
        # 移除<think>...</think>块
        if "<think>" in summary:
            import re
            summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
        return summary
    except Exception as e:
        print(f"LLM summarization failed for {album} - {artist}: {e}")
        return f"{artist} 的《{album}》，来自 {tags} 领域的推荐。"

# 处理low分组
if low:
    lines.append("\n## Also Recommended (★6)\n")
    for idx, r in enumerate(low):
        album = r.get("album", "(unknown)") or "(unknown)"
        artist = r.get("artist", "(unknown)") or "(unknown)"
        source = r.get("source", "") or r.get("_site", "") or "unknown"
        url = r.get("url", "#")
        excerpt = r.get("excerpt", "") or ""
        tags = r.get("tags", "") or ""
        score = r.get("total_score", 0)
        
        # 处理type区分
        rtype = r.get("type", "review")
        prefix = ""
        if rtype == "feature":
            prefix = "▸ [FEATURE] "
        elif rtype == "tracklist":
            prefix = "▸ [TRACKLIST] "
        
        print(f"Generating summary {idx+1}/{len(low)}: {album} - {artist}")
        summary = summarize_cn(artist, album, excerpt, tags)
        lines.append(f"{prefix}**{album}** —— *{artist}* [★{score}]/[{source}]({url})")
        lines.append(f"> {summary}\n")

# 写入最终markdown
md_path = os.path.join(BASE_DIR, f"recommend/{today}.md")
with open(md_path, "w") as f:
    f.write("\n".join(lines))

print(f"Done all {len(passed)} recommendations! Final markdown saved to {md_path}")
