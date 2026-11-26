"""Tiny deterministic quality eval with substring, number and JSON graders."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_EVALSET = Path(__file__).resolve().parents[2] / "config" / "evalset.yaml"
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class EvalItem:
    """One prompt with its grading rule."""

    id: str
    prompt: str
    kind: str
    expect: tuple[str, ...]


def load_evalset(path: Path = DEFAULT_EVALSET) -> list[EvalItem]:
    """Load eval items from YAML."""
    raw = yaml.safe_load(path.read_text())["items"]
    return [EvalItem(id=r["id"], prompt=r["prompt"], kind=r["kind"], expect=tuple(r["expect"])) for r in raw]


def _numbers(text: str) -> list[float]:
    return [float(n) for n in NUMBER_RE.findall(text.replace(",", ""))]


def grade(item: EvalItem, answer: str) -> bool:
    """Return True when the answer satisfies the item."""
    text = answer.strip().lower()
    if item.kind == "contains":
        return any(e.lower() in text for e in item.expect)
    if item.kind == "number":
        found = _numbers(text)
        return bool(found) and any(abs(found[-1] - float(e)) < 1e-9 for e in item.expect)
    if item.kind == "json_keys":
        match = JSON_RE.search(answer)
        if not match:
            return False
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            return False
        return isinstance(obj, dict) and all(k in obj for k in item.expect)
    raise ValueError(f"unknown grader kind: {item.kind}")
