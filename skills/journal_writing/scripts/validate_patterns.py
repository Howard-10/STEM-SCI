#!/usr/bin/env python3
"""Validate journal-writing YAML patterns and paper cards."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from _pattern_utils import SKILL_ROOT, exemplar_root

CARD_PATHS = (
    ("paper",),
    ("paper", "title"),
    ("paper", "journal"),
    ("paper", "year"),
    ("paper", "doi"),
    ("paper", "article_type"),
    ("paper", "methodology"),
    ("structure", "section_order"),
    ("introduction", "opening_strategy"),
    ("introduction", "problem_context"),
    ("introduction", "literature_review_strategy"),
    ("introduction", "research_gap", "explicit"),
    ("introduction", "research_gap", "position"),
    ("introduction", "research_gap", "description"),
    ("introduction", "theoretical_framework", "present"),
    ("introduction", "theoretical_framework", "position"),
    ("introduction", "theoretical_framework", "separate_section"),
    ("introduction", "research_questions", "present"),
    ("introduction", "research_questions", "position"),
    ("introduction", "contribution_statement", "present"),
    ("introduction", "contribution_statement", "position"),
    ("methods", "research_design"),
    ("methods", "participants_or_data"),
    ("methods", "sampling"),
    ("methods", "instruments"),
    ("methods", "procedure"),
    ("methods", "validity_reliability_or_trustworthiness"),
    ("methods", "analysis_method"),
    ("methods", "reproducibility_detail"),
    ("results", "organization"),
    ("results", "organized_by_research_questions"),
    ("results", "evidence_types"),
    ("results", "tables_usage"),
    ("results", "figures_usage"),
    ("results", "interpretation_level"),
    ("discussion", "opening_strategy"),
    ("discussion", "answers_research_questions"),
    ("discussion", "comparison_with_prior_research"),
    ("discussion", "theoretical_interpretation"),
    ("discussion", "practical_implications"),
    ("discussion", "educational_implications"),
    ("discussion", "limitations"),
    ("discussion", "future_work"),
    ("discussion", "conclusion_strategy"),
    ("writing_features", "theory_emphasis"),
    ("writing_features", "evidence_emphasis"),
    ("writing_features", "practical_implication_emphasis"),
    ("writing_features", "educational_implication_emphasis"),
    ("writing_features", "typical_argument_flow"),
    ("evidence", "source_type"),
)

MISSING = object()


def _get(data: Any, path: Iterable[str]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return MISSING
        current = current[key]
    return current


def _walk(data: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(data, dict):
        for key, value in data.items():
            current = path + (str(key),)
            yield current, value
            yield from _walk(value, current)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _walk(value, path + (str(index),))


def _load_all(errors: list[str]) -> dict[Path, Any]:
    roots = [SKILL_ROOT / "journals", SKILL_ROOT / "patterns", exemplar_root()]
    paths = sorted({path for root in roots if root.exists() for path in root.rglob("*.yaml")})
    loaded: dict[Path, Any] = {}
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as stream:
                loaded[path] = yaml.safe_load(stream)
        except (OSError, yaml.YAMLError) as error:
            errors.append(f"{path}: YAML parse failed: {error}")
    return loaded


def _check_numeric_invariants(path: Path, data: Any, errors: list[str]) -> None:
    for key_path, value in _walk(data):
        key = key_path[-1]
        location = ".".join(key_path)
        if key == "frequency" and value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1
        ):
            errors.append(f"{path}: {location} must be between 0 and 1")
    for key_path, value in _walk(data):
        if not isinstance(value, dict):
            continue
        evidence_count = value.get("evidence_count")
        sample_size = value.get("sample_size")
        if evidence_count is not None and sample_size is not None:
            if not isinstance(evidence_count, int) or not isinstance(sample_size, int):
                errors.append(f"{path}: {'.'.join(key_path)} counts must be integers")
            elif evidence_count > sample_size:
                errors.append(f"{path}: {'.'.join(key_path)} evidence_count exceeds sample_size")


def _check_guideline(path: Path, data: Any, errors: list[str]) -> None:
    expected = path.stem.removesuffix("_submission_guidelines")
    actual = _get(data, ("journal", "id"))
    if actual is not MISSING and actual != expected:
        errors.append(f"{path}: journal.id {actual!r} does not match filename {expected!r}")


def _check_pattern(path: Path, data: Any, errors: list[str]) -> None:
    relative = path.relative_to(SKILL_ROOT / "patterns")
    if relative.parts[0] == "general":
        expected = "general_pattern"
    elif relative.parts[0] == "methodology":
        expected = "methodology_pattern"
    elif relative.parts[0] == "journals":
        expected = "observed_pattern"
    else:
        errors.append(f"{path}: unknown pattern layer")
        return
    if not isinstance(data, dict) or data.get("pattern_type") != expected:
        errors.append(f"{path}: pattern_type must be {expected}")
        return
    if expected == "methodology_pattern" and data.get("methodology") != path.stem:
        errors.append(f"{path}: methodology must match filename")
    if expected == "observed_pattern":
        journal_id = _get(data, ("journal", "id"))
        if journal_id != path.stem:
            errors.append(f"{path}: journal.id must match filename")
        for key_path, value in _walk(data):
            key = key_path[-1].casefold()
            if (key == "required" and value is True) or value in ("official_rule", "official_submission_guideline"):
                errors.append(f"{path}: observed pattern contains an official-rule marker at {'.'.join(key_path)}")


def _check_card(path: Path, data: Any, errors: list[str]) -> None:
    if not isinstance(data, dict):
        errors.append(f"{path}: paper card must be a mapping")
        return
    for required_path in CARD_PATHS:
        if _get(data, required_path) is MISSING:
            errors.append(f"{path}: missing field {'.'.join(required_path)}")
    journal = _get(data, ("paper", "journal"))
    expected = path.parent.parent.name
    if journal is not MISSING and journal != expected:
        errors.append(f"{path}: paper.journal {journal!r} does not match directory {expected!r}")
    if _get(data, ("evidence", "source_type")) != "published_article":
        errors.append(f"{path}: evidence.source_type must be published_article")
    section_order = _get(data, ("structure", "section_order"))
    evidence_types = _get(data, ("results", "evidence_types"))
    argument_flow = _get(data, ("writing_features", "typical_argument_flow"))
    for label, value in (
        ("structure.section_order", section_order),
        ("results.evidence_types", evidence_types),
        ("writing_features.typical_argument_flow", argument_flow),
    ):
        if value is not MISSING and not isinstance(value, list):
            errors.append(f"{path}: {label} must be a list")


def validate() -> list[str]:
    errors: list[str] = []
    loaded = _load_all(errors)
    journal_root = SKILL_ROOT / "journals"
    pattern_root = SKILL_ROOT / "patterns"
    exemplar = exemplar_root()
    for path, data in loaded.items():
        if not isinstance(data, (dict, list)):
            errors.append(f"{path}: YAML document must be a mapping or list")
            continue
        _check_numeric_invariants(path, data, errors)
        if journal_root in path.parents:
            _check_guideline(path, data, errors)
        elif pattern_root in path.parents:
            _check_pattern(path, data, errors)
        elif exemplar in path.parents and path.parent.name == "cards":
            _check_card(path, data, errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"validation failed: {len(errors)} error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
