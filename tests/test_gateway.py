"""Gateway config rendering."""

import yaml

from openllm.cli import GATEWAY_PATHS
from openllm.gateway import build_gateway_config, env_slug, render_gateway_yaml
from openllm.registry import load_registry


def test_env_slug() -> None:
    assert env_slug("qwen2.5-0.5b") == "QWEN2_5_0_5B"


def test_every_model_has_cpu_and_pinned_routes() -> None:
    registry = load_registry()
    names = {d["model_name"] for d in build_gateway_config(registry)["model_list"]}
    for model in registry.models:
        assert {model.name, f"{model.name}@cpu"} <= names
        if model.vllm:
            assert f"{model.name}@gpu" in names
    assert {"llamacpp", *registry.aliases} <= names


def test_gpu_preferred_over_cpu_in_same_group() -> None:
    config = build_gateway_config(load_registry())
    group = [d for d in config["model_list"] if d["model_name"] == "qwen2.5-1.5b"]
    orders = {d["model_info"]["backend"]: d["litellm_params"]["order"] for d in group}
    assert orders == {"vllm": 1, "ollama": 2}


def test_no_literal_secrets_or_urls_in_config() -> None:
    for deployment in build_gateway_config(load_registry())["model_list"]:
        params = deployment["litellm_params"]
        assert params["api_base"].startswith("os.environ/")
        assert params.get("api_key", "none") in {"none", "os.environ/VLLM_API_KEY"}


def test_alias_fallbacks_follow_registry_order() -> None:
    registry = load_registry()
    fallbacks = {
        k: v
        for item in build_gateway_config(registry)["litellm_settings"]["fallbacks"]
        for k, v in item.items()
    }
    for alias, targets in registry.aliases.items():
        assert fallbacks[alias] == targets[1:]


def test_committed_configs_are_fresh() -> None:
    expected = render_gateway_yaml(load_registry())
    for path in GATEWAY_PATHS:
        assert path.read_text() == expected, f"{path} is stale; run make gateway"
    assert yaml.safe_load(expected)["model_list"]
