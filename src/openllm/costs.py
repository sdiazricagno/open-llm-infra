"""Cost estimates: which models fit where and what a million tokens costs at a given throughput."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from openllm.registry import Model, Registry

DEFAULT_COSTS = Path(__file__).resolve().parents[2] / "config" / "costs.yaml"


@dataclass(frozen=True)
class Instance:
    """A priced compute option."""

    id: str
    provider: str
    accelerator: str
    vram_gb: float
    usd_per_hour: float
    billing: str
    source: str


def load_instances(path: Path = DEFAULT_COSTS) -> tuple[str, list[Instance]]:
    """Return the price check date and the instances."""
    data = yaml.safe_load(path.read_text())
    return str(data["checked"]), [Instance(**i) for i in data["instances"]]


def usd_per_million_tokens(usd_per_hour: float, tokens_per_second: float) -> float:
    """Cost of one million generated tokens at full utilisation."""
    if tokens_per_second <= 0:
        raise ValueError("tokens_per_second must be positive")
    return usd_per_hour / (tokens_per_second * 3600) * 1_000_000


def monthly_usd(usd_per_hour: float, hours_per_day: float = 24.0, days: float = 30.0) -> float:
    """Monthly cost for a given duty cycle."""
    return usd_per_hour * hours_per_day * days


def fits(model: Model, instance: Instance) -> bool:
    """True when the model's vLLM build fits the instance's VRAM."""
    return model.vllm is not None and instance.vram_gb >= model.vllm.min_vram_gb


def fit_matrix(registry: Registry, instances: list[Instance]) -> dict[str, list[str]]:
    """Instance ids each model fits on for GPU serving."""
    gpu = [i for i in instances if i.vram_gb > 0]
    return {m.name: [i.id for i in gpu if fits(m, i)] for m in registry.models}
