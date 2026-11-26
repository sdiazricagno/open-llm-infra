"""Quality graders."""

import pytest

from openllm.evalset import EvalItem, grade, load_evalset


def _item(kind: str, *expect: str) -> EvalItem:
    return EvalItem(id="t", prompt="p", kind=kind, expect=expect)


@pytest.mark.parametrize(
    ("answer", "ok"),
    [("391", True), ("17 * 23 = 391", True), ("The answer is 391.", True), ("392", False), ("none", False)],
)
def test_number_grader_uses_last_number(answer: str, ok: bool) -> None:
    assert grade(_item("number", "391"), answer) is ok


def test_contains_grader_case_insensitive() -> None:
    assert grade(_item("contains", "canberra"), "Canberra.")
    assert not grade(_item("contains", "canberra"), "Sydney")


def test_json_grader() -> None:
    item = _item("json_keys", "city", "country")
    assert grade(item, '```json\n{"city": "Paris", "country": "France"}\n```')
    assert not grade(item, '{"city": "Paris"}')
    assert not grade(item, "not json")


def test_shipped_evalset_is_well_formed() -> None:
    items = load_evalset()
    assert len(items) >= 20
    assert len({i.id for i in items}) == len(items)
    assert {i.kind for i in items} <= {"contains", "number", "json_keys"}
