"""Reference-only code specification and artifact contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from stem_sci.core.models import DomainModel


class CodeSpecification(DomainModel):
    specification_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    input_refs: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)
    random_seed: int | None = None

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
