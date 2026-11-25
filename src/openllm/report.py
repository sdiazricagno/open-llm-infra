"""Turn benchmark JSON into README tables and charts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from openllm.costs import usd_per_million_tokens


def load_reports(results_dir: Path) -> list[dict[str, Any]]:
    """Load every benchmark JSON in a directory, sorted by model size then name."""
    reports = [json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json"))]
    return sorted(reports, key=lambda r: (r.get("params_b", 0.0), r["model"]))


def _level(report: dict[str, Any], concurrency: int) -> dict[str, Any] | None:
    return next((c for c in report["concurrency"] if c["concurrency"] == concurrency), None)


def summary_rows(reports: list[dict[str, Any]], cpu_usd_per_hour: float) -> list[dict[str, Any]]:
    """Flatten reports into one row per model."""
    rows = []
    for r in reports:
        single = _level(r, 1)
        levels = sorted(r["concurrency"], key=lambda c: c["concurrency"])
        peak = max(levels, key=lambda c: c["aggregate_tps"]) if levels else None
        quality = r.get("quality") or {}
        rows.append(
            {
                "model": r["model"],
                "backend": r["backend"],
                "size_gb": r.get("size_gb"),
                "cold_start_s": r.get("cold_start_s"),
                "ttft_p50_s": single["ttft_p50_s"] if single else None,
                "decode_tps": single["decode_tps_mean"] if single else None,
                "latency_p50_s": single["latency_p50_s"] if single else None,
                "peak_concurrency": peak["concurrency"] if peak else None,
                "peak_tps": peak["aggregate_tps"] if peak else None,
                "accuracy": quality.get("accuracy"),
                "quality_n": quality.get("total"),
                "usd_per_m_tokens": (
                    round(usd_per_million_tokens(cpu_usd_per_hour, peak["aggregate_tps"]), 2)
                    if peak and peak["aggregate_tps"] > 0
                    else None
                ),
            }
        )
    return rows


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_table(rows: list[dict[str, Any]]) -> str:
    """Render the summary as a markdown table."""
    header = (
        "| Model (Q4_K_M) | GGUF GB | Load s | TTFT p50 s | Decode tok/s (1 user) | p50 latency s "
        "| Peak tok/s (users) | Quality | Est. $/1M tok on c7i.2xlarge |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    lines = []
    for r in rows:
        quality = "-"
        if r["accuracy"] is not None:
            quality = f"{round(r['accuracy'] * r['quality_n'])}/{r['quality_n']}"
        peak = f"{_fmt(r['peak_tps'], 1)} ({r['peak_concurrency']})" if r["peak_tps"] is not None else "-"
        lines.append(
            f"| {r['model']} | {_fmt(r['size_gb'])} | {_fmt(r['cold_start_s'], 1)} | {_fmt(r['ttft_p50_s'])} "
            f"| {_fmt(r['decode_tps'], 1)} | {_fmt(r['latency_p50_s'], 1)} | {peak} | {quality} "
            f"| {_fmt(r['usd_per_m_tokens'])} |"
        )
    return header + "\n".join(lines) + "\n"


def plot_throughput(reports: list[dict[str, Any]], out: Path) -> None:
    """Bar chart of aggregate tokens/sec per model at each concurrency level."""
    levels = sorted({c["concurrency"] for r in reports for c in r["concurrency"]})
    width = 0.8 / max(len(levels), 1)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, level in enumerate(levels):
        xs = [j + i * width for j in range(len(reports))]
        ys = [(_level(r, level) or {}).get("aggregate_tps", 0.0) for r in reports]
        bars = ax.bar(xs, ys, width=width, label=f"{level} concurrent user{'s' if level > 1 else ''}")
        ax.bar_label(bars, fmt="%.1f", fontsize=8, padding=2)
    ax.set_xticks([j + width * (len(levels) - 1) / 2 for j in range(len(reports))])
    ax.set_xticklabels([r["model"] for r in reports])
    ax.set_ylabel("generated tokens / second")
    ax.set_title("llama.cpp on 8 vCPU (no GPU), Q4_K_M: aggregate generation throughput")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_quality_speed(rows: list[dict[str, Any]], out: Path) -> None:
    """Scatter of single-user decode speed against eval accuracy."""
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for r in rows:
        if r["decode_tps"] is None or r["accuracy"] is None:
            continue
        ax.scatter(r["decode_tps"], r["accuracy"] * 100, s=60 + (r["size_gb"] or 0) * 120, alpha=0.7)
        point = (r["decode_tps"], r["accuracy"] * 100)
        ax.annotate(r["model"], point, textcoords="offset points", xytext=(6, 6))
    ax.set_xlabel("decode tokens / second (1 user)")
    ax.set_ylabel("eval accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Speed vs quality on CPU (bubble size = GGUF size)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
