"""Command line entry point: `python -m openllm <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from openllm import bench, costs, gateway, report
from openllm.evalset import load_evalset
from openllm.registry import DEFAULT_REGISTRY, load_registry

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_PATHS = [
    ROOT / "gateway" / "litellm.yaml",
    ROOT / "deploy" / "helm" / "open-llm" / "files" / "litellm.yaml",
]


def cmd_gateway(args: argparse.Namespace) -> int:
    """Render or check the gateway config."""
    registry = load_registry(Path(args.registry))
    expected = gateway.render_gateway_yaml(registry)
    if args.check:
        stale = [str(p) for p in GATEWAY_PATHS if not p.exists() or p.read_text() != expected]
        if stale:
            print("gateway config out of date, run `make gateway`: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("gateway config up to date")
        return 0
    gateway.write_gateway(registry, GATEWAY_PATHS)
    print("wrote " + ", ".join(str(p.relative_to(ROOT)) for p in GATEWAY_PATHS))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    """Print the model matrix with GPU fit."""
    registry = load_registry(Path(args.registry))
    _, instances = costs.load_instances()
    matrix = costs.fit_matrix(registry, instances)
    print("| Model | Params (B) | License | Context | GGUF Q4_K_M GB | Ollama tag | vLLM repo | Fits (GPU) |")
    print("|---|---:|---|---:|---:|---|---|---|")
    for m in registry.models:
        repo = f"{m.vllm.repo}{' (gated)' if m.vllm.gated else ''}" if m.vllm else "-"
        fit = ", ".join(i.removeprefix("aws-").removeprefix("gcp-") for i in matrix[m.name]) or "-"
        print(
            f"| {m.name} | {m.params_b} | {m.license} | {m.context} | {m.gguf.size_gb:.2f} "
            f"| `{m.ollama}` | `{repo}` | {fit} |"
        )
    return 0


def cmd_costs(args: argparse.Namespace) -> int:
    """Print the instance price table, optionally with $/1M tokens at a throughput."""
    checked, instances = costs.load_instances()
    print(f"Estimated list prices, checked {checked}. Verify before budgeting.\n")
    extra = f" | $/1M tok @ {args.tps:g} tok/s" if args.tps else ""
    print(f"| Option | Accelerator | VRAM GB | $/hour | $/month 24x7 | Billing{extra} | Source |")
    print("|---|---|---:|---:|---:|---|" + ("---:|" if args.tps else "") + "---|")
    for i in instances:
        per_m = f" | {costs.usd_per_million_tokens(i.usd_per_hour, args.tps):.2f}" if args.tps else ""
        print(
            f"| {i.id} | {i.accelerator} | {i.vram_gb:g} | {i.usd_per_hour:.4f} "
            f"| {costs.monthly_usd(i.usd_per_hour):,.0f} | {i.billing}{per_m} | [link]({i.source}) |"
        )
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Benchmark one model on one OpenAI-compatible endpoint and write JSON."""
    started = datetime.now(UTC).isoformat(timespec="seconds")
    load = bench.load_avg()
    cold = bench.wait_ready(args.base_url, args.model, api_key=args.api_key) if args.wait else None
    levels = [
        bench.run_concurrency(
            args.base_url, args.model, c, max(args.requests, c), args.max_tokens, args.api_key
        )
        for c in args.concurrency
    ]
    quality = None
    if not args.skip_quality:
        quality = bench.run_quality(args.base_url, args.model, load_evalset(), api_key=args.api_key)
    result = bench.BenchReport(
        model=args.label or args.model,
        base_url=args.base_url,
        backend=args.backend,
        started_at=started,
        host=bench.host_info(),
        load_avg_start=load,
        cold_start_s=round(cold, 2) if cold is not None else None,
        concurrency=levels,
        quality=quality,
    ).to_dict()
    if args.registry_name:
        model = load_registry().get(args.registry_name)
        result["params_b"] = model.params_b
        result["size_gb"] = model.gguf.size_gb
    result["max_tokens"] = args.max_tokens
    result["load_avg_end"] = bench.load_avg()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("model", "cold_start_s", "concurrency")}, indent=2))
    if quality:
        print(f"quality {quality.correct}/{quality.total}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Build the README table and charts from benchmark JSON."""
    _, instances = costs.load_instances()
    cpu_price = next(i.usd_per_hour for i in instances if i.id == args.cpu_instance)
    reports = report.load_reports(Path(args.results))
    rows = report.summary_rows(reports, cpu_price)
    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)
    report.plot_throughput(reports, docs / "cpu_throughput.png")
    report.plot_quality_speed(rows, docs / "cpu_speed_vs_quality.png")
    table = report.markdown_table(rows)
    (docs / "benchmark_table.md").write_text(table)
    print(table)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for all commands."""
    parser = argparse.ArgumentParser(prog="openllm", description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gateway", help="render the LiteLLM gateway config from the registry")
    g.add_argument("--check", action="store_true", help="fail if the committed config is stale")
    g.set_defaults(func=cmd_gateway)

    sub.add_parser("models", help="print the model matrix").set_defaults(func=cmd_models)

    c = sub.add_parser("costs", help="print estimated instance prices")
    c.add_argument("--tps", type=float, default=0.0, help="throughput to convert into $/1M tokens")
    c.set_defaults(func=cmd_costs)

    b = sub.add_parser("bench", help="benchmark an OpenAI-compatible endpoint")
    b.add_argument("--base-url", required=True, help="e.g. http://localhost:4000/v1")
    b.add_argument("--model", required=True)
    b.add_argument("--label", default=None)
    b.add_argument("--registry-name", default=None)
    b.add_argument("--backend", default="openai-compatible")
    b.add_argument("--api-key", default=None)
    b.add_argument("--concurrency", type=int, nargs="+", default=[1, 4])
    b.add_argument("--requests", type=int, default=8)
    b.add_argument("--max-tokens", type=int, default=128)
    b.add_argument("--skip-quality", action="store_true")
    b.add_argument("--wait", action="store_true", help="measure time until the endpoint first answers")
    b.add_argument("--out", required=True)
    b.set_defaults(func=cmd_bench)

    r = sub.add_parser("report", help="tables and charts from benchmark results")
    r.add_argument("--results", default=str(ROOT / "results"))
    r.add_argument("--docs", default=str(ROOT / "docs"))
    r.add_argument("--cpu-instance", default="aws-c7i.2xlarge")
    r.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
