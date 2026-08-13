"""Optional, audit-safe structured generation for planning and design Agents.

These pipelines add model-assisted *candidate rationale* to deterministic
protocol compilers.  They never approve a design, determine a result, or
replace the deterministic candidate objects emitted by the Agents.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents.runtime import GenerationResult, PromptRegistry, StructuredGenerator

from .design_contracts import ResearchDesignBrief
from .planning_contracts import PlanningBrief


class _GenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanningRationaleCandidate(_GenerationModel):
    primary_question_rationale: str = Field(min_length=1)
    feasibility_assumptions: list[str] = Field(min_length=1)
    feasibility_risks: list[str] = Field(min_length=1)
    evidence_needs: list[str] = Field(min_length=1)
    unresolved_questions: list[str] = Field(min_length=1)


class DesignRationaleCandidate(_GenerationModel):
    estimand_rationale: str = Field(min_length=1)
    allocation_risk_notes: list[str] = Field(min_length=1)
    measurement_validity_questions: list[str] = Field(min_length=1)
    analysis_boundary_notes: list[str] = Field(min_length=1)
    preregistration_risks: list[str] = Field(min_length=1)


class MentorPlanningPipeline:
    """One typed LLM call for a bounded planning rationale."""

    def __init__(
        self, *, generator: StructuredGenerator, model: str, prompt_registry: PromptRegistry | None = None
    ) -> None:
        self.generator = generator
        self.model = model
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.prompt_registry.register(
            name="mentor_planning_rationale",
            version="mentor-planning-v1",
            system_prompt=(
                "You are a research-planning assistant. Produce a bounded candidate rationale from "
                "the supplied brief only. Do not claim empirical effects, approve feasibility, invent "
                "citations, or change the research scope."
            ),
            user_prompt_template="Planning brief JSON:\n{payload}",
        )

    def run(self, brief: PlanningBrief) -> GenerationResult:
        system, user = self.prompt_registry.render(
            "mentor_planning_rationale",
            "mentor-planning-v1",
            payload=_json(brief.model_dump(mode="json")),
        )
        return self.generator.generate(
            system_prompt=system,
            user_prompt=user,
            response_model=PlanningRationaleCandidate,
            model=self.model,
            prompt_version="mentor-planning-v1",
        )


class ResearchDesignPipeline:
    """One typed LLM call for bounded design rationale and risk questions."""

    def __init__(
        self, *, generator: StructuredGenerator, model: str, prompt_registry: PromptRegistry | None = None
    ) -> None:
        self.generator = generator
        self.model = model
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.prompt_registry.register(
            name="research_design_rationale",
            version="research-design-v1",
            system_prompt=(
                "You are a research-design assistant. Produce only candidate rationale and explicit "
                "risks from the supplied brief. Do not approve ethics, assert causal identification, "
                "alter preregistered decisions, or generate statistical results."
            ),
            user_prompt_template="Research design brief JSON:\n{payload}",
        )

    def run(self, brief: ResearchDesignBrief) -> GenerationResult:
        system, user = self.prompt_registry.render(
            "research_design_rationale",
            "research-design-v1",
            payload=_json(brief.model_dump(mode="json")),
        )
        return self.generator.generate(
            system_prompt=system,
            user_prompt=user,
            response_model=DesignRationaleCandidate,
            model=self.model,
            prompt_version="research-design-v1",
        )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
