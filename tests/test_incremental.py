"""07:00 增量评分测试（pytest）。用 tests/fakeanth 假 SDK，不联网、不碰真实仓库。

每个测试在 tmp_path 里搭沙箱：bin/ + data/ 拷贝、本地 bare origin、
先跑一次 04:00 全量（--skip-scrape --skip-swarm），再跑 daily_watchdog.py（--if-needed）。
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATE = "2026-10-14"
SUB = Path("2026/10") / DATE


def item(n, url=None, **kw):
    d = {"album": f"Album {n}", "artist": f"Artist {n}", "url": url or f"https://site.com/review/{n}",
         "source": "Test", "site_id": "test", "pub_date": DATE, "body": f"review body number {n} " * 20}
    d.update(kw)
    return d


def sh(cmd, cwd, env=None, check=True):
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, capture_output=True)


class Sandbox:
    def __init__(self, tmp: Path):
        self.root = tmp / "repo"
        self.origin = tmp / "origin.git"
        self.log = tmp / "calls.log"
        self.root.mkdir()
        shutil.copytree(REPO / "bin", self.root / "bin", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "data", self.root / "data")
        (self.root / ".gitignore").write_text("__pycache__/\n")
        sh(["git", "init", "-q", "--bare", str(self.origin)], tmp)
        for c in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@t"],
                  ["git", "config", "user.name", "test"], ["git", "add", "-A"],
                  ["git", "commit", "-qm", "init"],
                  ["git", "remote", "add", "origin", str(self.origin)],
                  ["git", "push", "-q", "origin", "main"]):
            sh(c, self.root)
        self.dd = self.root / SUB
        self.dd.mkdir(parents=True)

    def env(self, mode="ok"):
        e = dict(os.environ)
        e.update(MUSIC_RECORD_ROOT=str(self.root), MINIMAX_CN_API_KEY="fake", FAKE_MODE=mode,
                 FAKE_LOG=str(self.log),
                 PYTHONPATH=str(REPO / "tests" / "fakeanth"))
        return e

    def calls(self):
        return len(self.log.read_text().splitlines()) if self.log.exists() else 0

    def reset_calls(self):
        self.log.write_text("")

    def write(self, name, items):
        (self.dd / name).write_text(json.dumps({"meta": {}, "items": items}, ensure_ascii=False))

    def full_run(self, mode="ok"):
        r = sh([sys.executable, "bin/daily_pipeline.py", "--date", DATE, "--skip-scrape", "--skip-swarm"],
               self.root, self.env(mode))
        return r

    def watchdog(self, mode="ok"):
        time.sleep(1.1)  # 保证尾巴 mtime 晚于 processed.json
        return sh([sys.executable, "bin/daily_watchdog.py", "--date", DATE], self.root, self.env(mode))

    def touch_tail(self, name, items):
        time.sleep(1.1)
        self.write(name, items)

    def origin_commits(self):
        return int(sh(["git", "rev-list", "--count", "main"], self.origin).stdout.strip())

    def processed(self):
        return json.loads((self.dd / "processed.json").read_text())

    def scores(self):
        return {i["url"]: i["total_score"] for i in self.processed()["items"]}

    def report(self):
        return (self.root / "recommend/2026/10" / f"{DATE}.md").read_bytes()


def setup(tmp_path, n=6):
    sb = Sandbox(tmp_path)
    sb.write("rss_merged.json", [item(i) for i in range(n)])
    sb.full_run()
    assert sb.calls() == n
    sb.reset_calls()
    return sb


def test_empty_tail_no_calls_no_commit(tmp_path):
    sb = setup(tmp_path)
    c0, s0, rep0 = sb.origin_commits(), sb.scores(), sb.report()
    raw0 = (sb.dd / "scraped_raw.json").read_bytes()
    sb.touch_tail("jazztokyo_reviews.json", [])
    r = sb.watchdog()
    assert "status=noop" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 0
    assert sb.origin_commits() == c0
    assert sb.scores() == s0 and sb.report() == rep0
    assert (sb.dd / "scraped_raw.json").read_bytes() == raw0


def test_one_new_item_one_call_scores_frozen(tmp_path):
    sb = setup(tmp_path)
    c0, s0 = sb.origin_commits(), sb.scores()
    sb.touch_tail("boomkat_reviews.json", [item("late", site_id="boomkat")])
    r = sb.watchdog()
    assert "status=updated" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 1
    s1 = sb.scores()
    for u, sc in s0.items():
        assert s1[u] == sc
    assert "https://site.com/review/late" in s1
    assert sb.origin_commits() == c0 + 1
    # 再跑一次 watchdog：没有新东西 → 0 调用、0 提交
    sb.reset_calls()
    sb.touch_tail("musicircus_reviews.json", [])
    sb.watchdog()
    assert sb.calls() == 0 and sb.origin_commits() == c0 + 1


def test_url_variant_is_not_new(tmp_path):
    sb = setup(tmp_path)
    c0, rep0 = sb.origin_commits(), sb.report()
    variants = [
        item(1, url="http://SITE.com/review/1/"),
        item(2, url="https://site.com/review/2?utm_source=rss&utm_medium=feed"),
        item(3, url="https://site.com/review/3/?fbclid=abc123"),
    ]
    sb.touch_tail("point_of_departure_reviews.json", variants)
    r = sb.watchdog()
    assert "status=noop" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 0 and sb.origin_commits() == c0 and sb.report() == rep0


def test_incremental_all_fail_keeps_report(tmp_path):
    sb = setup(tmp_path)
    c0, rep0 = sb.origin_commits(), sb.report()
    proc0 = (sb.dd / "processed.json").read_bytes()
    sb.touch_tail("wild_city_reviews.json", [item("x1"), item("x2")])
    r = sb.watchdog(mode="allfail")
    assert "status=all-failed" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 2 * 3  # 2 条 × (1 + RETRIES=2)
    assert sb.report() == rep0
    assert (sb.dd / "processed.json").read_bytes() == proc0
    assert sb.origin_commits() == c0


def test_failed_items_retried_successes_frozen(tmp_path):
    """04:00 有失败条目 → 07:00 只重试失败的那几条，成功的分数不动。"""
    sb = Sandbox(tmp_path)
    sb.write("rss_merged.json", [item(i) for i in range(4)])
    sb.full_run(mode="allfail")          # 04:00 全挂：4 条都有 _score_error
    meta = sb.processed()["meta"]
    assert len(meta["score_error_keys"]) == 4 and meta["scored_keys"] == []
    sb.reset_calls()
    sb.touch_tail("boomkat_reviews.json", [])
    r = sb.watchdog()                     # 报告在 origin 上 → 增量，重试 4 条
    assert "status=updated" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 4
    s1 = sb.scores()
    assert len(sb.processed()["meta"]["score_error_keys"]) == 0
    sb.reset_calls()
    sb.touch_tail("musicircus_reviews.json", [])
    sb.watchdog()
    assert sb.calls() == 0 and sb.scores() == s1


def test_low_scores_not_rescored(tmp_path):
    """<=2 分被物理删除的条目仍在 scored_keys 里，07:00 不会被当成新条目重评。"""
    sb = Sandbox(tmp_path)
    spam = item("spam", body="best casinos not on gamstop for uk players " * 10)
    sb.write("rss_merged.json", [item(i) for i in range(3)] + [spam])
    sb.full_run()
    assert sb.calls() == 3                      # spam 被预过滤，0 分，不调 API
    meta = sb.processed()["meta"]
    assert len(meta["scored_keys"]) == 4        # 被删的 0 分条目仍记为"已评"
    assert spam["url"] not in sb.scores()       # 已物理删除
    sb.reset_calls()
    sb.touch_tail("jazztokyo_reviews.json", [])
    sb.watchdog()
    assert sb.calls() == 0


def test_url_norm_unit():
    sys.path.insert(0, str(REPO / "bin"))
    from url_norm import normalize_url as n
    assert n("http://Site.COM/a/") == n("https://site.com/a") == "https://site.com/a"
    assert n("https://site.com/a?utm_source=x&id=2&fbclid=y") == "https://site.com/a?id=2"
    assert n("https://site.com/a?b=2&a=1") == n("https://site.com/a?a=1&b=2")
    assert n("https://site.com/a#frag") == "https://site.com/a"
    assert n("") == ""


def test_legacy_processed_without_keys(tmp_path):
    """旧版 processed.json（无 scored_keys）：以 04:00 时的 scraped_raw 为已评集合。"""
    sb = setup(tmp_path)
    p = sb.processed()
    p["meta"].pop("scored_keys"); p["meta"].pop("score_error_keys")
    (sb.dd / "processed.json").write_text(json.dumps(p, ensure_ascii=False))
    s0 = sb.scores()
    sb.touch_tail("boomkat_reviews.json", [item(2, url="http://site.com/review/2/"), item("new1")])
    r = sb.watchdog()
    assert "status=updated" in r.stdout, r.stdout + r.stderr
    assert sb.calls() == 1
    assert all(sb.scores()[u] == s for u, s in s0.items())
