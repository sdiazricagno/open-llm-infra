"""Model registry loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


@dataclass(frozen=True)
class GGUF:
    """A quantised GGUF artefact on Hugging Face."""

    repo: str
    file: str
    size_gb: float

    @property
    def url(self) -> str:
        """Direct download URL."""
        return f"https://huggingface.co/{self.repo}/resolve/main/{self.file}"


@dataclass(frozen=True)
class VLLMSpec:
    """A Hugging Face repo served by vLLM on GPU."""

    repo: str
    gated: bool
    min_vram_gb: float


@dataclass(frozen=True)
class Model:
    """One open-weight model and how each backend serves it."""

    name: str
    family: str
    params_b: float
    license: str
    context: int
    tier: str
    gguf: GGUF
    ollama: str
    vllm: VLLMSpec | None = None


@dataclass(frozen=True)
class Registry:
    """All models plus routing aliases."""

    models: tuple[Model, ...]
    aliases: dict[str, list[str]] = field(default_factory=dict)

    def get(self, name: str) -> Model:
        """Return a model by name."""
        for model in self.models:
            if model.name == name:
                return model
        raise KeyError(f"unknown model: {name}")

    @property
    def names(self) -> list[str]:
        """Model names in registry order."""
        return [m.name for m in self.models]


def _parse_model(raw: dict[str, Any]) -> Model:
    vllm = raw.get("vllm")
    return Model(
        name=str(raw["name"]),
        family=str(raw["family"]),
        params_b=float(raw["params_b"]),
        license=str(raw["license"]),
        context=int(raw["context"]),
        tier=str(raw["tier"]),
        gguf=GGUF(**raw["gguf"]),
        ollama=str(raw["ollama"]),
        vllm=VLLMSpec(**vllm) if vllm else None,
    )


def parse_registry(data: dict[str, Any]) -> Registry:
    """Build and validate a registry from parsed YAML."""
    models = tuple(_parse_model(m) for m in data.get("models", []))
    if not models:
        raise ValueError("registry has no models")
    names = [m.name for m in models]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"duplicate model names: {duplicates}")
    aliases = {str(k): [str(x) for x in v] for k, v in (data.get("aliases") or {}).items()}
    for alias, targets in aliases.items():
        if alias in names:
            raise ValueError(f"alias shadows a model name: {alias}")
        missing = [t for t in targets if t not in names]
        if missing or not targets:
            raise ValueError(f"alias {alias} points at unknown models: {missing}")
    return Registry(models=models, aliases=aliases)


def load_registry(path: Path = DEFAULT_REGISTRY) -> Registry:
    """Load the registry from YAML."""
    return parse_registry(yaml.safe_load(path.read_text()))
