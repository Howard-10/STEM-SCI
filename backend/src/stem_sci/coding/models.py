"""Traceable specifications and artifacts for research-code generation.

``CodeSpecification`` is deliberately a Controller-owned compilation target:
an Agent may propose a draft, but a real specification has to bind an approved
executable plan to one frozen-data hash before a coding provider can be used.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.core.models import DomainModel


class CodeSpecification(DomainModel):
    specification_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    purpose: Literal["generic", "research_analysis"] = "generic"
    project_id: str | None = None
    executable_plan_ref: str | None = None
    frozen_dataset_ref: str | None = None
    frozen_dataset_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    analysis_dataset_ref: str | None = None
    analysis_dataset_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    deterministic_template_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    model_specification_ref: str | None = None
    approved_variable_names: list[str] = Field(default_factory=list)
    analysis_parameters: dict[str, str] = Field(default_factory=dict)
    execution_policy_ref: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)
    random_seed: int | None = None

    @model_validator(mode="after")
    def validate_research_analysis_binding(self) -> "CodeSpecification":
        """Prevent an analysis request from being detached from its evidence.

        ``generic`` keeps the small pre-existing contract usable for unrelated
        future operators.  A formal research-analysis specification, however,
        is invalid unless it is fully scoped to one project, plan and frozen
        dataset.  This is what makes a provider unable to silently choose a
        different data version.
        """

        if self.purpose == "research_analysis":
            required = {
                "project_id": self.project_id,
                "executable_plan_ref": self.executable_plan_ref,
                "frozen_dataset_ref": self.frozen_dataset_ref,
                "frozen_dataset_sha256": self.frozen_dataset_sha256,
                "model_specification_ref": self.model_specification_ref,
                "execution_policy_ref": self.execution_policy_ref,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(
                    "research_analysis code specifications require " + ", ".join(missing)
                )
            if not self.approved_variable_names:
                raise ValueError("research_analysis code specifications require approved variables")
            if not self.analysis_parameters:
                raise ValueError("research_analysis code specifications require analysis parameters")
            if self.analysis_parameters.get("requires_analysis_dataset") == "true":
                if (
                    not self.analysis_dataset_ref
                    or not self.analysis_dataset_sha256
                    or not self.deterministic_template_sha256
                ):
                    raise ValueError("v1 analysis specifications require a bound AnalysisDataset")
        return self

    @property
    def ref(self) -> str:
        return f"code-spec://{self.specification_id}"


class CodeArtifact(DomainModel):
    artifact_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    specification_ref: str = Field(min_length=1)
    content_uri: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
    language: str = "python"
    provider_id: str = "unspecified"
    provider_version: str = "unspecified"
    generation_status: Literal["generated", "provider_unavailable", "rejected"] = "generated"
    code_review_ref: str | None = None
    source_specification_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @property
    def ref(self) -> str:
        return f"code-artifact://{self.artifact_id}"
