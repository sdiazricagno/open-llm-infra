"""Registry parsing and validation."""

import pytest

from openllm.registry import load_registry, parse_registry


def _model(name: str) -> dict:
    return {
        "name": name,
        "family": "x",
        "params_b": 1,
        "license": "MIT",
        "context": 4096,
        "tier": "tiny",
        "gguf": {"repo": "a/b", "file": "c.gguf", "size_gb": 1.0},
        "ollama": "x:1b",
    }


def test_shipped_registry_loads() -> None:
    registry = load_registry()
    assert len(registry.models) >= 8
    assert {"fast", "balanced", "quality"} <= set(registry.aliases)
    assert registry.get("qwen2.5-0.5b").gguf.url.endswith("qwen2.5-0.5b-instruct-q4_k_m.gguf")


def test_duplicate_names_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        parse_registry({"models": [_model("a"), _model("a")]})


def test_alias_to_unknown_model_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        parse_registry({"models": [_model("a")], "aliases": {"fast": ["b"]}})


def test_alias_shadowing_model_rejected() -> None:
    with pytest.raises(ValueError, match="shadows"):
        parse_registry({"models": [_model("a")], "aliases": {"a": ["a"]}})


def test_unknown_model_lookup() -> None:
    with pytest.raises(KeyError):
        load_registry().get("nope")
