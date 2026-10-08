import json

from verifix.llm.client import GroqClient


def _fake(calls):
    def transport(body):
        calls.append(body)
        return {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
    return transport


def test_cache_avoids_second_call_and_counts_tokens(tmp_path):
    calls = []
    c = GroqClient(api_key="k", cache_dir=str(tmp_path), transport=_fake(calls))
    msgs = [{"role": "user", "content": "x"}]
    a = c.chat("m", msgs)
    b = c.chat("m", msgs)
    assert (a.text, a.tokens, b.cached, b.tokens) == ("hi", 7, True, 0)
    assert len(calls) == 1 and c.total_tokens == 7
    assert json.loads(next(tmp_path.iterdir()).read_text())["choices"]
