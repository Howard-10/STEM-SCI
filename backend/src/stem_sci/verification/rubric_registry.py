"""Versioned research-test rubric registry."""

from __future__ import annotations

from pydantic import Field

from stem_sci.core.models import DomainModel


class ResearchRubric(DomainModel):
    rubric_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)


class RubricRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ResearchRubric] = {}

    def register(self, rubric: ResearchRubric) -> ResearchRubric:
        key = (rubric.rubric_id, rubric.version)
        if key in self._items:
            raise ValueError("rubric version already registered")
        self._items[key] = rubric
        return rubric

    def get(self, rubric_id: str, version: str) -> ResearchRubric:
        try:
            return self._items[(rubric_id, version)]
        except KeyError as exc:
            raise ValueError(f"unknown rubric: {rubric_id}@{version}") from exc
