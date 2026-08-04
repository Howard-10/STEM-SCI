"""Versioned, reference-only dataset contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from stem_sci.core.models import DomainModel


class DatasetRef(DomainModel):
    dataset_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    content_uri: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime

    @property
    def ref(self) -> str:
        return f"dataset://{self.dataset_id}/{self.version}"


class RawDatasetRef(DatasetRef):
    pass


class ProcessedDatasetRef(DatasetRef):
    source_dataset_ref: str = Field(min_length=1)


class FrozenDatasetRef(DatasetRef):
    source_dataset_ref: str = Field(min_length=1)
    freeze_approval_ref: str = Field(min_length=1)
    frozen_at: datetime

    @model_validator(mode="after")
    def validate_frozen_source(self) -> FrozenDatasetRef:
        if self.frozen_at < self.created_at:
            raise ValueError("frozen_at cannot precede created_at")
        return self
