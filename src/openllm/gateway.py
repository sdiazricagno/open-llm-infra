"""Render one LiteLLM gateway config from the model registry for every environment."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from openllm.registry import Model, Registry

HEADER = (
    "# Rendered from config/models.yaml by `make gateway`; edit the registry, not this file.\n"
    "# Backends are resolved from environment variables, so the same file serves compose, k8s and cloud.\n"
)


def env_slug(name: str) -> str:
    """Turn a model name into an environment-variable-safe slug."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def vllm_env_var(model: Model) -> str:
    """Environment variable holding the vLLM base URL for a model."""
    return f"VLLM_{env_slug(model.name)}_API_BASE"


def _gpu_deployment(model: Model, name: str) -> dict[str, Any]:
    assert model.vllm is not None
    return {
        "model_name": name,
        "litellm_params": {
            "model": f"hosted_vllm/{model.vllm.repo}",
            "api_base": f"os.environ/{vllm_env_var(model)}",
            "api_key": "os.environ/VLLM_API_KEY",
            "order": 1,
        },
        "model_info": {"backend": "vllm", "family": model.family, "params_b": model.params_b},
    }


def _cpu_deployment(model: Model, name: str) -> dict[str, Any]:
    return {
        "model_name": name,
        "litellm_params": {
            "model": f"ollama_chat/{model.ollama}",
            "api_base": "os.environ/OLLAMA_API_BASE",
            "order": 2,
        },
        "model_info": {"backend": "ollama", "family": model.family, "params_b": model.params_b},
    }


def deployments_for(model: Model, name: str | None = None) -> list[dict[str, Any]]:
    """GPU-first, CPU-second deployments for one model group."""
    group = name or model.name
    out = [_gpu_deployment(model, group)] if model.vllm else []
    out.append(_cpu_deployment(model, group))
    return out


def build_gateway_config(registry: Registry) -> dict[str, Any]:
    """Build the LiteLLM proxy config dict."""
    model_list: list[dict[str, Any]] = []
    for model in registry.models:
        model_list.extend(deployments_for(model))
        model_list.append(_cpu_deployment(model, f"{model.name}@cpu"))
        if model.vllm:
            model_list.append(_gpu_deployment(model, f"{model.name}@gpu"))
    model_list.append(
        {
            "model_name": "llamacpp",
            "litellm_params": {
                "model": "openai/local",
                "api_base": "os.environ/LLAMACPP_API_BASE",
                "api_key": "none",
            },
            "model_info": {"backend": "llama.cpp"},
        }
    )
    fallbacks: list[dict[str, list[str]]] = []
    for alias, targets in registry.aliases.items():
        model_list.extend(deployments_for(registry.get(targets[0]), alias))
        if len(targets) > 1:
            fallbacks.append({alias: targets[1:]})
    return {
        "model_list": model_list,
        "router_settings": {
            "routing_strategy": "simple-shuffle",
            "num_retries": 1,
            "timeout": 300,
            "allowed_fails": 1,
            "cooldown_time": 30,
        },
        "litellm_settings": {
            "callbacks": ["prometheus"],
            "fallbacks": fallbacks,
            "drop_params": True,
            "request_timeout": 300,
        },
        "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY"},
    }


def render_gateway_yaml(registry: Registry) -> str:
    """Render the config as YAML text with a header."""
    return HEADER + yaml.safe_dump(build_gateway_config(registry), sort_keys=False, width=110)


def write_gateway(registry: Registry, paths: list[Path]) -> None:
    """Write the rendered config to every path."""
    text = render_gateway_yaml(registry)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
