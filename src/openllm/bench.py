"""Benchmark any OpenAI-compatible endpoint: latency, TTFT, decode speed, concurrency and quality."""

from __future__ import annotations

import json
import math
import os
import platform
import statistics
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from openllm.evalset import EvalItem, grade

THROUGHPUT_PROMPTS = (
    "Explain in about 120 words why caching matters for web applications.",
    "Write a short paragraph describing how a refrigerator keeps food cold.",
    "Summarise the main steps of training a machine learning model in plain English.",
    "Describe a sunrise over the mountains in a few sentences.",
)


@dataclass(frozen=True)
class RequestResult:
    """Timing and token counts for one streamed completion."""

    ttft_s: float
    total_s: float
    completion_tokens: int
    prompt_tokens: int
    text: str

    @property
    def decode_tps(self) -> float:
        """Tokens per second after the first token."""
        decode_time = self.total_s - self.ttft_s
        if decode_time <= 0 or self.completion_tokens < 2:
            return 0.0
        return (self.completion_tokens - 1) / decode_time


@dataclass
class ConcurrencyResult:
    """Aggregate numbers for one concurrency level."""

    concurrency: int
    requests: int
    wall_s: float
    total_completion_tokens: int
    aggregate_tps: float
    ttft_p50_s: float
    ttft_p95_s: float
    latency_p50_s: float
    latency_p95_s: float
    decode_tps_mean: float


@dataclass
class QualityResult:
    """Score on the eval set."""

    correct: int
    total: int
    accuracy: float
    failures: list[dict[str, str]] = field(default_factory=list)


@dataclass
class BenchReport:
    """Full benchmark output for one model on one endpoint."""

    model: str
    base_url: str
    backend: str
    started_at: str
    host: dict[str, Any]
    load_avg_start: list[float]
    cold_start_s: float | None
    concurrency: list[ConcurrencyResult]
    quality: QualityResult | None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to plain dict."""
        return asdict(self)


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile, q in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(q / 100 * len(ordered))))
    return ordered[rank - 1]


def iter_sse(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Yield JSON payloads from an OpenAI-style server-sent event stream."""
    for line in lines:
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        if payload:
            yield json.loads(payload)


def stream_chat(
    client: httpx.Client,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float = 0.0,
    api_key: str | None = None,
) -> RequestResult:
    """Send one streamed chat completion and time it."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    start = time.perf_counter()
    ttft: float | None = None
    chunks = 0
    parts: list[str] = []
    usage: dict[str, Any] = {}
    url = f"{base_url.rstrip('/')}/chat/completions"
    with client.stream("POST", url, json=body, headers=headers) as resp:
        resp.raise_for_status()
        for event in iter_sse(resp.iter_lines()):
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content") or ""
                if delta:
                    if ttft is None:
                        ttft = time.perf_counter() - start
                    chunks += 1
                    parts.append(delta)
    total = time.perf_counter() - start
    return RequestResult(
        ttft_s=ttft if ttft is not None else total,
        total_s=total,
        completion_tokens=int(usage.get("completion_tokens") or chunks),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        text="".join(parts),
    )


def run_concurrency(
    base_url: str,
    model: str,
    concurrency: int,
    requests: int,
    max_tokens: int,
    api_key: str | None = None,
    timeout_s: float = 600.0,
) -> ConcurrencyResult:
    """Fire `requests` completions with `concurrency` in flight and aggregate."""
    prompts = [THROUGHPUT_PROMPTS[i % len(THROUGHPUT_PROMPTS)] for i in range(requests)]
    with httpx.Client(timeout=timeout_s) as client, ThreadPoolExecutor(max_workers=concurrency) as pool:
        start = time.perf_counter()
        results = list(
            pool.map(lambda p: stream_chat(client, base_url, model, p, max_tokens, 0.7, api_key), prompts)
        )
        wall = time.perf_counter() - start
    tokens = sum(r.completion_tokens for r in results)
    ttfts = [r.ttft_s for r in results]
    lats = [r.total_s for r in results]
    return ConcurrencyResult(
        concurrency=concurrency,
        requests=requests,
        wall_s=round(wall, 3),
        total_completion_tokens=tokens,
        aggregate_tps=round(tokens / wall, 2) if wall > 0 else 0.0,
        ttft_p50_s=round(percentile(ttfts, 50), 3),
        ttft_p95_s=round(percentile(ttfts, 95), 3),
        latency_p50_s=round(percentile(lats, 50), 3),
        latency_p95_s=round(percentile(lats, 95), 3),
        decode_tps_mean=round(statistics.fmean(r.decode_tps for r in results), 2),
    )


def run_quality(
    base_url: str,
    model: str,
    items: Sequence[EvalItem],
    max_tokens: int = 48,
    api_key: str | None = None,
    timeout_s: float = 300.0,
) -> QualityResult:
    """Score the model on the eval set with greedy decoding."""
    failures: list[dict[str, str]] = []
    correct = 0
    with httpx.Client(timeout=timeout_s) as client:
        for item in items:
            answer = stream_chat(client, base_url, model, item.prompt, max_tokens, api_key=api_key).text
            if grade(item, answer):
                correct += 1
            else:
                failures.append({"id": item.id, "answer": answer.strip()[:200]})
    return QualityResult(
        correct=correct,
        total=len(items),
        accuracy=round(correct / len(items), 3) if items else 0.0,
        failures=failures,
    )


def wait_ready(base_url: str, model: str, timeout_s: float = 600.0, api_key: str | None = None) -> float:
    """Block until the endpoint answers a 1-token request; return seconds waited."""
    start = time.perf_counter()
    last_error: Exception | None = None
    with httpx.Client(timeout=60.0) as client:
        while time.perf_counter() - start < timeout_s:
            try:
                stream_chat(client, base_url, model, "Say ok.", 1, api_key=api_key)
                return time.perf_counter() - start
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(1.0)
    raise TimeoutError(f"{base_url} not ready after {timeout_s}s: {last_error}")


def host_info() -> dict[str, Any]:
    """Describe the machine the benchmark runs on."""
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as fh:
            names = [ln.split(":", 1)[1].strip() for ln in fh if ln.startswith("model name")]
        cpu = names[0] if names else cpu
    except OSError:
        pass
    return {
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "os": platform.platform(),
        "python": platform.python_version(),
    }


def load_avg() -> list[float]:
    """1/5/15 minute load averages, empty where unsupported."""
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except OSError:
        return []
