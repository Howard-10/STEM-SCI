"""Deterministic trigger-to-Agent routing rules."""

from __future__ import annotations

from pydantic import Field

from stem_sci.core.models import DomainModel


class RouteRule(DomainModel):
    rule_id: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)


class RulePolicy:
    def __init__(self, rules: list[RouteRule] | None = None) -> None:
        self._rules = {rule.trigger: rule for rule in (rules or [])}

    def resolve(self, trigger: str) -> RouteRule:
        try:
            return self._rules[trigger]
        except KeyError as exc:
            raise ValueError(f"no rule for trigger: {trigger}") from exc
