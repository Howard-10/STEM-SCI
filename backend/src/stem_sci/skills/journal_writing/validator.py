"""Deterministic and model-assisted journal compliance validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

from .loader import JournalProfileLoader
from .models import (
    DraftJournalValidation,
    JournalValidationFinding,
    JournalValidationStatus,
    JournalWritingConstraints,
    SemanticAssessmentResponse,
    ValidationCheckStatus,
)


class DraftLike(Protocol):
    @property
    def language(self) -> object: ...

    @property
    def sections(self) -> Mapping[str, str]: ...


def _normal(value: str) -> str:
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE).casefold()


def semantic_rule_keys(
    constraints: JournalWritingConstraints,
) -> set[tuple[str | None, str, str]]:
    keys: set[tuple[str | None, str, str]] = set()
    for section, rules in constraints.section_constraints.items():
        keys.update((section, "common_flow", rule) for rule in rules.common_flow)
        keys.update((section, "emphasis", rule) for rule in rules.emphasis)
        keys.update((section, "avoid", rule) for rule in rules.avoid)
    deterministically_checked = {"abstract_required", "keywords_required"}
    capability_only = {"latex_supported"}
    for key, value in constraints.format_rules.items():
        if key not in deterministically_checked | capability_only:
            keys.add((None, "format", f"{key}={value}"))
    return keys


def validate_journal_draft(
    draft: DraftLike,
    target_journal: str,
    article_type: str | None = None,
    semantic_assessment: SemanticAssessmentResponse | None = None,
    *,
    loader: JournalProfileLoader | None = None,
    methodology: str | None = None,
) -> DraftJournalValidation:
    active_loader = loader or JournalProfileLoader()
    constraints = active_loader.resolve_writing_constraints(target_journal, article_type, methodology=methodology)
    sections = list(draft.sections)
    section_map = {_normal(name): body for name, body in draft.sections.items()}
    findings: list[JournalValidationFinding] = []

    for required in constraints.required_sections:
        body = section_map.get(_normal(required))
        present = body is not None and bool(body.strip())
        findings.append(
            JournalValidationFinding(
                code="REQUIRED_SECTION",
                status=ValidationCheckStatus.PASS if present else ValidationCheckStatus.FAIL,
                section=required,
                rule_type="structure",
                rule=required,
                message=(
                    f"Required section {required!r} is present."
                    if present
                    else f"Required section {required!r} is missing or empty."
                ),
            )
        )

    positions = {_normal(name): index for index, name in enumerate(sections)}
    present_positions = [
        positions[_normal(name)]
        for name in constraints.required_sections
        if _normal(name) in positions
    ]
    order_ok = present_positions == sorted(present_positions)
    findings.append(
        JournalValidationFinding(
            code="SECTION_ORDER",
            status=ValidationCheckStatus.PASS if order_ok else ValidationCheckStatus.FAIL,
            rule_type="structure",
            rule="recommended_sections",
            message="Configured section order is satisfied." if order_ok else "Sections are out of order.",
        )
    )

    for key, section_name in (("abstract_required", "Abstract"), ("keywords_required", "Keywords")):
        if constraints.format_rules.get(key) is True:
            present = bool(section_map.get(_normal(section_name), "").strip())
            findings.append(
                JournalValidationFinding(
                    code=key.upper(),
                    status=ValidationCheckStatus.PASS if present else ValidationCheckStatus.FAIL,
                    section=section_name,
                    rule_type="format",
                    rule=f"{key}=true",
                    message=(
                        f"{section_name} is present."
                        if present
                        else f"{section_name} is required by the journal profile."
                    ),
                )
            )

    allowed = semantic_rule_keys(constraints)
    supplied = (
        {(item.section, item.rule_type, item.rule): item for item in semantic_assessment.assessments}
        if semantic_assessment is not None
        else {}
    )
    unknown = set(supplied) - allowed
    if unknown:
        raise ValueError("semantic assessment contains rules absent from journal configuration")
    for section, rule_type, rule in sorted(allowed, key=lambda item: str(item)):
        item = supplied.get((section, rule_type, rule))
        findings.append(
            JournalValidationFinding(
                code="SEMANTIC_RULE",
                status=item.status if item else ValidationCheckStatus.NOT_CHECKED,
                section=section,
                rule_type=rule_type,
                rule=rule,
                message=item.explanation if item else "Rule was not assessed.",
            )
        )

    statuses = {item.status for item in findings}
    if ValidationCheckStatus.FAIL in statuses:
        status = JournalValidationStatus.NON_COMPLIANT
    elif ValidationCheckStatus.NOT_CHECKED in statuses:
        status = JournalValidationStatus.INCOMPLETE
    else:
        status = JournalValidationStatus.PASS
    language = getattr(draft.language, "value", str(draft.language))
    return DraftJournalValidation(language=str(language), status=status, findings=findings)
