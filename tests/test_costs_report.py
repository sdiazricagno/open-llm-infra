"""Cost maths and report rendering."""

import json
from pathlib import Path

import pytest

from openllm import costs, report
from openllm.registry import load_registry


def test_usd_per_million_tokens() -> None:
    assert costs.usd_per_million_tokens(3.6, 1000) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        costs.usd_per_million_tokens(1.0, 0)


def test_price_table_has_sources() -> None:
    checked, instances = costs.load_instances()
    assert checked
    assert all(i.source.startswith("https://") and i.usd_per_hour > 0 for i in instances)


def test_fit_matrix_respects_vram() -> None:
    _, instances = costs.load_instances()
    matrix = costs.fit_matrix(load_registry(), instances)
    assert "aws-g4dn.xlarge" not in matrix["mistral-7b"]
    assert "aws-g6.xlarge" in matrix["mistral-7b"]


def test_report_from_results(tmp_path: Path) -> None:
    level = {
        "concurrency": 1,
        "requests": 2,
        "wall_s": 2.0,
        "total_completion_tokens": 40,
        "aggregate_tps": 20.0,
        "ttft_p50_s": 0.1,
        "ttft_p95_s": 0.2,
        "latency_p50_s": 1.0,
        "latency_p95_s": 1.1,
        "decode_tps_mean": 21.0,
    }
    data = {
        "model": "m",
        "backend": "llama.cpp",
        "params_b": 0.5,
        "size_gb": 0.5,
        "cold_start_s": 1.0,
        "concurrency": [level, {**level, "concurrency": 4, "aggregate_tps": 50.0}],
        "quality": {"correct": 3, "total": 4, "accuracy": 0.75, "failures": []},
    }
    (tmp_path / "m.json").write_text(json.dumps(data))
    rows = report.summary_rows(report.load_reports(tmp_path), cpu_usd_per_hour=0.36)
    assert rows[0]["peak_tps"] == 50.0
    assert rows[0]["usd_per_m_tokens"] == pytest.approx(2.0)
    table = report.markdown_table(rows)
    assert "| m |" in table and "3/4" in table
    report.plot_throughput(report.load_reports(tmp_path), tmp_path / "a.png")
    report.plot_quality_speed(rows, tmp_path / "b.png")
    assert (tmp_path / "a.png").stat().st_size > 0
