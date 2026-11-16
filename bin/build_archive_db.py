#!/usr/bin/env python3
"""把 recommend/ 下全部历史日报解析入 SQLite，按规范化标题去重。

产出 data/music_archive.db（可再生产物，不入 git）：
  albums      去重后的专辑级视图（best_score / 出现次数 / 首末日期 / 来源集合）
  appearances 每条原始出现记录（日期、文件、来源、URL、评分、引言）
  meta        构建统计

去重口径：标题整行做 NFKC + casefold + 空白折叠 + 破折号/引号归一。
只做精确规范化去重，不做跨来源模糊合并（Songlines 与 RootsWorld 写法
不一致的同一专辑仍会是两行）。

用法: python3 bin/build_archive_db.py
"""
import glob
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REC_DIR = REPO / "recommend"
DB_PATH = REPO / "data" / "music_archive.db"

RE_STYLE = re.compile(r"\*\*风格\*\*: (.+)")
RE_SCORE = re.compile(r"\*\*评分\*\*: (\d+)/10")
RE_SOURCE = re.compile(r"\*\*来源\*\*: \[(.+?)\]\((.+?)\)")
RE_QUOTE = re.compile(r"^> (.+)$", re.M)

DASHES = str.maketrans({
    "—": "-", "–": "-", "‑": "-", "‐": "-",
    "“": '"', "”": '"', "’": "'", "‘": "'",
})


def norm_key(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw).translate(DASHES)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s


def split_title_artist(heading: str):
    m = re.match(r"^(.*?)\s+—\s+(.*)$", heading)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return heading.strip(), None


def parse_file(path: Path):
    date = re.search(r"(\d{4}-\d{2}-\d{2})\.md$", path.name).group(1)
    txt = path.read_text(encoding="utf-8")
    for body in re.split(r"^### ", txt, flags=re.M)[1:]:
        heading = body.split("\n", 1)[0].strip()
        if not heading:
            continue
        style = RE_STYLE.search(body)
        score = RE_SCORE.search(body)
        src = RE_SOURCE.search(body)
        quote = RE_QUOTE.search(body)
        yield {
            "date": date,
            "file": str(path.relative_to(REPO)),
            "title_raw": heading,
            "key": norm_key(heading),
            "style": style.group(1).strip() if style else None,
            "score": int(score.group(1)) if score else None,
            "source": src.group(1).strip() if src else None,
            "url": src.group(2).strip() if src else None,
            "quote": quote.group(1).strip() if quote else None,
        }


def main():
    files = sorted(REC_DIR.glob("**/*.md"))
    if not files:
        sys.exit("no report files found")
    entries = [e for f in files for e in parse_file(f)]

    groups = defaultdict(list)
    for e in entries:
        groups[e["key"]].append(e)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE albums (
          id INTEGER PRIMARY KEY,
          norm_key TEXT UNIQUE NOT NULL,
          title TEXT NOT NULL,
          artist TEXT,
          best_score INTEGER,
          n_appearances INTEGER NOT NULL,
          first_date TEXT NOT NULL,
          last_date TEXT NOT NULL,
          sources TEXT,
          style TEXT,
          url TEXT
        );
        CREATE TABLE appearances (
          id INTEGER PRIMARY KEY,
          album_id INTEGER NOT NULL REFERENCES albums(id),
          date TEXT NOT NULL,
          file TEXT NOT NULL,
          title_raw TEXT NOT NULL,
          source TEXT,
          url TEXT,
          score INTEGER,
          style TEXT,
          quote TEXT
        );
        CREATE INDEX idx_appearances_date ON appearances(date);
        CREATE INDEX idx_appearances_album ON appearances(album_id);
        CREATE INDEX idx_albums_score ON albums(best_score);
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
        """
    )

    for key, items in groups.items():
        first = sorted(items, key=lambda e: (e["date"], e["file"]))[0]
        title, artist = split_title_artist(first["title_raw"])
        scores = [e["score"] for e in items if e["score"] is not None]
        sources = sorted({e["source"] for e in items if e["source"]})
        cur = con.execute(
            "INSERT INTO albums (norm_key, title, artist, best_score,"
            " n_appearances, first_date, last_date, sources, style, url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                key, title, artist,
                max(scores) if scores else None,
                len(items),
                min(e["date"] for e in items),
                max(e["date"] for e in items),
                " | ".join(sources),
                first["style"],
                first["url"],
            ),
        )
        album_id = cur.lastrowid
        con.executemany(
            "INSERT INTO appearances (album_id, date, file, title_raw,"
            " source, url, score, style, quote) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (album_id, e["date"], e["file"], e["title_raw"],
                 e["source"], e["url"], e["score"], e["style"], e["quote"])
                for e in sorted(items, key=lambda e: (e["date"], e["file"]))
            ],
        )

    n_files = len(files)
    con.executemany(
        "INSERT INTO meta (k, v) VALUES (?,?)",
        [
            ("built_from_files", str(n_files)),
            ("raw_entries", str(len(entries))),
            ("unique_albums", str(len(groups))),
            ("duplicate_entries", str(len(entries) - len(groups))),
        ],
    )
    con.commit()

    n_alb = con.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    n_app = con.execute("SELECT COUNT(*) FROM appearances").fetchone()[0]
    print(f"files={n_files} raw_entries={len(entries)} "
          f"unique_albums={n_alb} appearances={n_app} "
          f"dup_entries={len(entries)-len(groups)}")
    print(f"db size: {DB_PATH.stat().st_size/1024/1024:.1f} MB -> {DB_PATH}")


if __name__ == "__main__":
    main()
