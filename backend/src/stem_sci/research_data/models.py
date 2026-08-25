"""Versioned, reference-only dataset and deterministic-analysis contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.core.models import DomainModel


class DatasetRef(DomainModel):
    """A persisted dataset reference with byte-level and canonical integrity hashes."""

    dataset_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    content_uri: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    raw_bytes_sha256: str = ""
    canonical_content_sha256: str = ""
    created_at: datetime

    @model_validator(mode="after")
    def populate_compatibility_hashes(self) -> "DatasetRef":
        """Keep older persisted references readable while new writers set both hashes."""

        if not self.raw_bytes_sha256:
            self.raw_bytes_sha256 = self.sha256
        if not self.canonical_content_sha256:
            self.canonical_content_sha256 = self.sha256
        if len(self.raw_bytes_sha256) != 64 or len(self.canonical_content_sha256) != 64:
            raise ValueError("dataset hashes must be SHA256 values")
        return self

    @property
    def ref(self) -> str:
        return f"dataset://{self.dataset_id}/{self.version}"


class RawDatasetRef(DatasetRef):
    """Read-only original upload; its canonical hash is observational only."""


class ProcessedDatasetRef(DatasetRef):
    source_dataset_ref: str = Field(min_length=1)
    processing_plan_ref: str = Field(min_length=1)
    processing_approval_ref: str = Field(min_length=1)
    processed_at: datetime


class FrozenDatasetRef(DatasetRef):
    source_dataset_ref: str = Field(min_length=1)
    freeze_approval_ref: str = Field(min_length=1)
    schema_ref: str = Field(min_length=1)
    frozen_at: datetime

    @model_validator(mode="after")
    def validate_frozen_source(self) -> "FrozenDatasetRef":
        if self.frozen_at < self.created_at:
            raise ValueError("frozen_at cannot precede created_at")
        return self


class AnalysisDatasetSerializationPolicy(DomainModel):
    """Stable CSV representation used for content-addressed analysis datasets."""

    policy_id: str = "analysis-dataset-csv-v1"
    encoding: Literal["UTF-8"] = "UTF-8"
    line_ending: Literal["LF"] = "LF"
    column_order: Literal["schema-defined"] = "schema-defined"
    row_order: tuple[str, ...] = ("participant_id", "measurement_period", "task_id")
    null_representation: Literal[""] = ""
    float_serialization: Literal["deterministic"] = "deterministic"
    index: Literal[False] = False


class ParticipantEligibilityRecord(DomainModel):
    participant_id: str = Field(min_length=1)
    study_inclusion_status: Literal["eligible", "ineligible"]
    rule_ids: list[str] = Field(default_factory=list)


class ParticipantEligibilityManifest(DomainModel):
    manifest_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    frozen_dataset_ref: str = Field(min_length=1)
    frozen_dataset_sha256: str = Field(min_length=64, max_length=64)
    records: list[ParticipantEligibilityRecord] = Field(min_length=1)
    policy_version: str = "participant-eligibility-v1"

    @property
    def ref(self) -> str:
        return f"participant-eligibility://{self.manifest_id}"


class ModelEligibilityRecord(DomainModel):
    participant_id: str = Field(min_length=1)
    eligible: bool
    rule_ids: list[str] = Field(default_factory=list)


class ModelEligibilityManifest(DomainModel):
    manifest_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    model_id: Literal["primary_lmm", "transfer_ancova", "prompt_dependency_lmm"]
    source_frozen_dataset_ref: str = Field(min_length=1)
    source_dataset_sha256: str = Field(min_length=64, max_length=64)
    participant_eligibility_manifest_ref: str = Field(min_length=1)
    records: list[ModelEligibilityRecord] = Field(min_length=1)
    group_counts: dict[str, int] = Field(default_factory=dict)
    sequence_counts: dict[str, int] = Field(default_factory=dict)
    task_period_row_counts: dict[str, int] = Field(default_factory=dict)
    passed_minimum_coverage: bool
    minimum_group_size: int = Field(ge=1, default=24)
    minimum_group_sequence_size: int = Field(ge=1, default=12)
    policy_version: str = "model-eligibility-v1"

    @property
    def ref(self) -> str:
        return f"model-eligibility://{self.manifest_id}"


class AnalysisDatasetRef(DatasetRef):
    source_frozen_dataset_ref: str = Field(min_length=1)
    source_dataset_sha256: str = Field(min_length=64, max_length=64)
    data_processing_plan_ref: str = Field(min_length=1)
    analysis_dataset_specification_ref: str = Field(min_length=1)
    model_specification_ref: str = Field(min_length=1)
    participant_eligibility_manifest_ref: str = Field(min_length=1)
    model_eligibility_manifest_ref: str = Field(min_length=1)
    included_row_count: int = Field(ge=0)
    excluded_row_count: int = Field(ge=0)
    included_participant_count: int = Field(ge=0)
    serialization_policy_ref: str = Field(min_length=1)


class SyntheticDatasetGenerationManifest(DomainModel):
    manifest_id: str = Field(min_length=1)
    dataset_type: Literal["SYNTHETIC_DEMO"] = "SYNTHETIC_DEMO"
    generator_version: str = "demo_seed_v1"
    random_seed: int = 20260812
    participant_count: int = Field(ge=1)
    group_allocation_rule: str = Field(min_length=1)
    sequence_allocation_rule: str = Field(min_length=1)
    effect_parameters: dict[str, float] = Field(default_factory=dict)
    noise_parameters: dict[str, float] = Field(default_factory=dict)
    missingness_parameters: dict[str, float] = Field(default_factory=dict)
    generated_dataset_sha256: str = Field(min_length=64, max_length=64)
