"""Versioned skill manifests and their Controller-visible bindings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from stem_sci.context.models import StrictModel


class RiskLevel(StrEnum):
    """Risk classification used when routing a skill for policy checks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillManifest(StrictModel):
    """Declarative skill contract and the schemas/tools it binds together."""

    skill_id: str = Field(min_length=1)
    skill_version: str = Field(min_length=1)
    agent_ids: list[str] = Field(min_length=1)
    supported_task_types: list[str] = Field(min_length=1)
    required_tool_ids: list[str] = Field(min_length=1)
    input_schema_refs: list[str] = Field(min_length=1)
    output_schema_refs: list[str] = Field(min_length=1)
    prompt_template_refs: list[str] = Field(min_length=1)
    validator_refs: list[str] = Field(min_length=1)
    risk_level: RiskLevel
