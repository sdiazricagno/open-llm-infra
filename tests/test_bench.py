"""Benchmark client against a mocked OpenAI-compatible stream."""

import json

import httpx
import respx

from openllm import bench
from openllm.evalset import EvalItem

BASE = "http://test.local/v1"


def _sse(chunks: list[str], completion_tokens: int) -> bytes:
    events = [{"choices": [{"delta": {"content": c}}]} for c in chunks]
    events.append({"choices": [], "usage": {"completion_tokens": completion_tokens, "prompt_tokens": 7}})
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return body.encode()


def test_percentile_nearest_rank() -> None:
    assert bench.percentile([1, 2, 3, 4], 50) == 2
    assert bench.percentile([1, 2, 3, 4], 95) == 4
    assert bench.percentile([], 50) == 0.0


def test_decode_tps() -> None:
    result = bench.RequestResult(ttft_s=1.0, total_s=3.0, completion_tokens=21, prompt_tokens=5, text="")
    assert result.decode_tps == 10.0
    assert bench.RequestResult(1.0, 1.0, 1, 0, "").decode_tps == 0.0


@respx.mock
def test_stream_chat_reads_usage_and_text() -> None:
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(200, content=_sse(["Hel", "lo"], 2))
    )
    with httpx.Client() as client:
        result = bench.stream_chat(client, BASE, "m", "hi", 8)
    assert result.text == "Hello"
    assert result.completion_tokens == 2
    assert result.prompt_tokens == 7
    assert 0 <= result.ttft_s <= result.total_s


@respx.mock
def test_concurrency_and_quality() -> None:
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(200, content=_sse(["391"], 4)))
    level = bench.run_concurrency(BASE, "m", concurrency=2, requests=4, max_tokens=8)
    assert level.requests == 4
    assert level.total_completion_tokens == 16
    items = [EvalItem("a", "17*23?", "number", ("391",)), EvalItem("b", "cap?", "contains", ("paris",))]
    quality = bench.run_quality(BASE, "m", items)
    assert (quality.correct, quality.total) == (1, 2)
    assert quality.failures[0]["id"] == "b"
