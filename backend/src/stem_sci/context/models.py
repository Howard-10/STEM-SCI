"""Versioned models for the local context and evidence boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class VerificationStatus(StrEnum):
    DEMO_SEED = "demo_seed"
    MODEL_GENERATED_UNVERIFIED = "model_generated_unverified"
    SOURCE_VERIFIED = "source_verified"
    HUMAN_VERIFIED = "human_verified"


class EvidenceRelation(StrEnum):
    SUPPORTING = "supporting"
    CONTRASTING = "contrasting"
    MENTIONING = "mentioning"


class SourceLocation(BaseModel):
    chunk_index: int
    char_start: int
    char_end: int
    heading: str | None = None


class SourceDocument(BaseModel):
    source_id: str
    filename: str
    media_type: Literal["text/markdown", "text/plain", "application/json"]
    sha256: str
    storage_path: str = Field(exclude=True)
    imported_at: str
    verification_status: VerificationStatus = VerificationStatus.MODEL_GENERATED_UNVERIFIED


class SourceChunk(BaseModel):
    chunk_id: str
    source_id: str
    text: str
    location: SourceLocation


class EvidenceItem(BaseModel):
    evidence_id: str
    source_id: str
    chunk_id: str
    excerpt: str
    relation: EvidenceRelation = EvidenceRelation.MENTIONING
    verification_status: VerificationStatus


class EvidenceRef(BaseModel):
    evidence_id: str
    source_id: str
    chunk_id: str
    excerpt: str
    location: SourceLocation
    verification_status: VerificationStatus


class PaperCard(BaseModel):
    paper_card_id: str
    source_id: str
    title: str
    evidence_refs: list[str] = Field(default_factory=list)


class MemoryRef(BaseModel):
    memory_id: str
    summary: str
    source_refs: list[str] = Field(default_factory=list)


class ContextBuildRequest(BaseModel):
    task_ref: str
    query: str
    required_context_types: list[str] = Field(default_factory=lambda: ["evidence"])
    token_budget: int = Field(gt=0, le=20_000)
    allowed_verification_statuses: list[VerificationStatus] = Field(
        default_factory=lambda: [VerificationStatus.SOURCE_VERIFIED, VerificationStatus.HUMAN_VERIFIED]
    )


class ContextBundle(BaseModel):
    context_id: str
    task_ref: str
    query: str
    evidence_refs: list[EvidenceRef]
    source_refs: list[str]
    memory_refs: list[MemoryRef] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    verification_summary: dict[str, int]
    token_budget: int
    estimated_tokens: int
    context_hash: str
    generated_at: str


class EvidenceSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    allowed_verification_statuses: list[VerificationStatus] = Field(default_factory=list)


class EvidenceSearchResult(BaseModel):
    evidence: EvidenceRef
    score: float


class EvidenceDetail(EvidenceRef):
    relation: EvidenceRelation
    verification_note: str | None = None
    verified_by: str | None = None
    verified_at: str | None = None
