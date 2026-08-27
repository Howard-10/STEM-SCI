"""Typed contracts for journal-specific manuscript constraints."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class JournalWritingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JournalIdentity(JournalWritingModel):
    name: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    field: str | None = None


class JournalSource(JournalWritingModel):
    url: str = Field(min_length=1)
    publisher: str | None = None
    verified_date: str | None = None


class ManuscriptStructure(JournalWritingModel):
    recommended_sections: list[str] = Field(min_length=1)


class JournalSectionStyle(JournalWritingModel):
    emphasis: list[str] = Field(default_factory=list)


class JournalProfile(JournalWritingModel):
    journal: JournalIdentity
    aliases: list[str] = Field(default_factory=list)
    source: JournalSource | None = None
    article_types: list[str] = Field(min_length=1)
    submission_rules: dict[str, JsonValue] = Field(default_factory=dict)
    structure: ManuscriptStructure
    writing_style: dict[str, JournalSectionStyle] = Field(default_factory=dict)
    format: dict[str, JsonValue] = Field(default_factory=dict)
    ethics: dict[str, JsonValue] = Field(default_factory=dict)
    data: dict[str, JsonValue] = Field(default_factory=dict)
    template: dict[str, JsonValue] = Field(default_factory=dict)


class SectionWritingPattern(JournalWritingModel):
    purpose: str = Field(min_length=1)
    common_flow: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class WritingPatterns(JournalWritingModel):
    writing_patterns: dict[str, SectionWritingPattern] = Field(min_length=1)


class SectionWritingConstraint(JournalWritingModel):
    purpose: str | None = None
    common_flow: list[str] = Field(default_factory=list)
    emphasis: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class JournalWritingConstraints(JournalWritingModel):
    target_journal: str
    article_type: str
    required_sections: list[str]
    format_rules: dict[str, JsonValue] = Field(default_factory=dict)
    section_constraints: dict[str, SectionWritingConstraint] = Field(default_factory=dict)
    submission_rules: dict[str, JsonValue] = Field(default_factory=dict)
    ethics_rules: dict[str, JsonValue] = Field(default_factory=dict)
    data_rules: dict[str, JsonValue] = Field(default_factory=dict)
    template: dict[str, JsonValue] = Field(default_factory=dict)
    methodology: str | None = None
    style_layers: dict[str, JsonValue] = Field(default_factory=dict)


class ArticleTypeRecommendation(JournalWritingModel):
    target_journal: str = Field(min_length=1)
    recommended_type: str = Field(min_length=1)
    allowed_types: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    requires_confirmation: bool = True


class ValidationCheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CHECKED = "NOT_CHECKED"


class JournalValidationStatus(StrEnum):
    PASS = "PASS"
    INCOMPLETE = "INCOMPLETE"
    NON_COMPLIANT = "NON_COMPLIANT"


class JournalValidationFinding(JournalWritingModel):
    code: str = Field(min_length=1)
    status: ValidationCheckStatus
    message: str = Field(min_length=1)
    section: str | None = None
    rule_type: str | None = None
    rule: str | None = None


class SemanticRuleAssessment(JournalWritingModel):
    section: str | None
    rule_type: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    status: ValidationCheckStatus
    explanation: str = Field(min_length=1)


class SemanticAssessmentResponse(JournalWritingModel):
    assessments: list[SemanticRuleAssessment]


class DraftJournalValidation(JournalWritingModel):
    language: str
    status: JournalValidationStatus
    findings: list[JournalValidationFinding] = Field(default_factory=list)


class JournalValidationReport(JournalWritingModel):
    project_id: str = Field(min_length=1)
    target_journal: str = Field(min_length=1)
    article_type: str = Field(min_length=1)
    status: JournalValidationStatus
    drafts: list[DraftJournalValidation] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
