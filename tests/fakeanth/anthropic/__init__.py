"""Fake anthropic SDK for tests: deterministic scores, every call logged.

FAKE_MODE=ok (default) → score 3..10 from md5(prompt); allfail → raise.
FAKE_LOG=path → one line appended per messages.create call.
"""
import hashlib
import json
import os


class _Blk:
    type = "text"

    def __init__(self, t):
        self.text = t


class _Msg:
    def __init__(self, t):
        self.content = [_Blk(t)]


class _Messages:
    def create(self, model, max_tokens, temperature, messages):
        prompt = messages[0]["content"]
        with open(os.environ.get("FAKE_LOG", "/tmp/fake_anthropic_calls.log"), "a") as f:
            f.write("call\n")
        if os.environ.get("FAKE_MODE", "ok") == "allfail":
            raise Exception("Connection error.")
        h = int(hashlib.md5(prompt.encode()).hexdigest(), 16)
        return _Msg(json.dumps({"total_score": 3 + h % 8, "genre": "test / fake",
                                "cn_summary": "测试摘要"}, ensure_ascii=False))


class Anthropic:
    def __init__(self, **kw):
        self.messages = _Messages()
