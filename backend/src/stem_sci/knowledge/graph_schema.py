"""Versioned contracts for the optional GraphRAG extraction layer.

These models describe graph navigation material; they do not execute an LLM,
write to Neo4j, or promote graph triples to formal evidence.  A graph triple
is therefore always explicitly marked as ``model_generated_unverified`` until
an evidence workflow verifies the underlying source excerpt.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GraphEntityType(StrEnum):
    """Closed core vocabulary used by the STEM education graph."""

    RESEARCH_METHOD = "ResearchMethod"
    EDUCATIONAL_THEORY = "EducationalTheory"
    TECHNOLOGY = "Technology"
    PEDAGOGICAL_METHOD = "PedagogicalMethod"
    SUBJECT_DOMAIN = "SubjectDomain"
    LEARNING_OUTCOME = "LearningOutcome"
    STUDENT_POPULATION = "StudentPopulation"
    ASSESSMENT = "Assessment"
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    EFFECT_SIZE = "EffectSize"
    SAMPLE_INFO = "SampleInfo"
    COMPARISON_CONDITION = "ComparisonCondition"
    CONCEPT = "Concept"
    PAPER = "Paper"
    REPORTING_GUIDELINE = "ReportingGuideline"


class GraphRelationType(StrEnum):
    """Relations allowed in the versioned graph artifact."""

    USES_METHOD = "USES_METHOD"
    ADOPTS_PEDAGOGY = "ADOPTS_PEDAGOGY"
    APPLIES_THEORY = "APPLIES_THEORY"
    DEPLOYS_TECH = "DEPLOYS_TECH"
    STUDIES_DOMAIN = "STUDIES_DOMAIN"
    TARGETS_OUTCOME = "TARGETS_OUTCOME"
    INVOLVES_POPULATION = "INVOLVES_POPULATION"
    EMPLOYS_ASSESSMENT = "EMPLOYS_ASSESSMENT"
    HAS_SAMPLE = "HAS_SAMPLE"
    INTEGRATES_WITH = "INTEGRATES_WITH"
    IMPROVES = "IMPROVES"
    CLAIMS = "CLAIMS"
    SUPPORTED_BY = "SUPPORTED_BY"
    HAS_EFFECT_SIZE = "HAS_EFFECT_SIZE"
    COMPARES_WITH = "COMPARES_WITH"
    RELATED_TO = "RELATED_TO"


class GraphExtractionMode(StrEnum):
    """The amount of source text an extraction request is allowed to inspect."""

    PROFILE = "PROFILE"
    EVIDENCE = "EVIDENCE"
    FULL_AUDIT = "FULL_AUDIT"


_PAPER_HEAD_RELATIONS = {
    GraphRelationType.USES_METHOD,
    GraphRelationType.ADOPTS_PEDAGOGY,
    GraphRelationType.APPLIES_THEORY,
    GraphRelationType.DEPLOYS_TECH,
    GraphRelationType.STUDIES_DOMAIN,
    GraphRelationType.TARGETS_OUTCOME,
    GraphRelationType.INVOLVES_POPULATION,
    GraphRelationType.EMPLOYS_ASSESSMENT,
    GraphRelationType.HAS_SAMPLE,
    GraphRelationType.CLAIMS,
}


class GraphModel(BaseModel):
    """Strict boundary for graph artifacts."""

    model_config = ConfigDict(extra="forbid")


class GraphExtractionRequest(GraphModel):
    """Controller-approved source metadata for a future extraction operator."""

    project_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list, max_length=100)
    mode: GraphExtractionMode = GraphExtractionMode.PROFILE
    schema_version: str = Field(min_length=1)


class GraphTriple(GraphModel):
    """One graph edge with source provenance and no verification claim."""

    project_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    head: str = Field(min_length=1)
    head_type: GraphEntityType
    relation: GraphRelationType
    tail: str = Field(min_length=1)
    tail_type: GraphEntityType
    evidence: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    layer: Literal["L2", "L3"] = "L2"
    source_chunk_id: str | None = None
    source_chunk_index: int | None = Field(default=None, ge=0)
    source_status: Literal["model_generated_unverified"] = "model_generated_unverified"
    new_type_suggestion: str | None = None

    @model_validator(mode="after")
    def validate_provenance_and_shape(self) -> "GraphTriple":
        if self.relation in _PAPER_HEAD_RELATIONS and self.head_type is not GraphEntityType.PAPER:
            raise ValueError(f"{self.relation.value} requires a Paper head")
        if (
            self.head_type is GraphEntityType.CONCEPT
            or self.tail_type is GraphEntityType.CONCEPT
            or self.relation is GraphRelationType.RELATED_TO
        ) and not self.new_type_suggestion:
            raise ValueError("open-vocabulary graph items require new_type_suggestion")
        if (self.source_chunk_id is None) != (self.source_chunk_index is None):
            raise ValueError("source_chunk_id and source_chunk_index must be provided together")
        return self

class GraphExtractionResult(GraphModel):
    """Immutable candidate result from a future graph extraction operator."""

    extraction_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    mode: GraphExtractionMode
    triples: list[GraphTriple] = Field(default_factory=list)
    source_status: Literal["model_generated_unverified"] = "model_generated_unverified"

    @model_validator(mode="after")
    def require_project_and_paper_scope(self) -> "GraphExtractionResult":
        if any(
            triple.project_id != self.project_id or triple.paper_id != self.paper_id
            for triple in self.triples
        ):
            raise ValueError("all graph triples must belong to the extraction project and paper")
        if any(triple.source_status != self.source_status for triple in self.triples):
            raise ValueError("graph result and triples must use the same verification status")
        return self
