#!/usr/bin/env python3
"""Aggregate paper cards into an evidence-counted observed journal pattern."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable
from typing import Any

from _pattern_utils import (
    SKILL_ROOT,
    card_files,
    dump_yaml,
    load_yaml,
    ordered_present_fields,
)

METHOD_FIELDS = (
    "research_design",
    "participants_or_data",
    "sampling",
    "instruments",
    "procedure",
    "validity_reliability_or_trustworthiness",
    "analysis_method",
    "reproducibility_detail",
)
RESULT_FIELDS = (
    "organization",
    "evidence_types",
    "tables_usage",
    "figures_usage",
    "interpretation_level",
)
DISCUSSION_FIELDS = (
    "opening_strategy",
    "answers_research_questions",
    "comparison_with_prior_research",
    "theoretical_interpretation",
    "practical_implications",
    "educational_implications",
    "limitations",
    "future_work",
    "conclusion_strategy",
)


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _mode(values: Iterable[Any]) -> Any:
    usable = [str(value) for value in values if value not in (None, "", [])]
    return Counter(usable).most_common(1)[0][0] if usable else None


def _observed_boolean(
    cards: list[dict[str, Any]],
    path: tuple[str, ...],
    *,
    position_path: tuple[str, ...] | None = None,
    evidence_basis: str,
    unknown_as_absent: bool,
) -> dict[str, Any]:
    values = [_nested(card, *path) for card in cards]
    count = sum(value is True for value in values)
    sample_size = len(cards)
    analyzed_count = sample_size if unknown_as_absent else sum(isinstance(value, bool) for value in values)
    denominator = sample_size if unknown_as_absent else analyzed_count
    result: dict[str, Any] = {
        "common": count / denominator >= 0.5 if denominator else None,
        "evidence_basis": evidence_basis,
    }
    if position_path:
        result["typical_position"] = _mode(_nested(card, *position_path) for card in cards)
    result.update(
        {
            "evidence_count": count,
            "analyzed_count": analyzed_count,
            "sample_size": sample_size,
            "frequency": round(count / denominator, 2) if denominator else None,
        }
    )
    return result


def _common_flow(cards: list[dict[str, Any]], section: str, fields: tuple[str, ...]) -> list[str]:
    threshold = max(1, (len(cards) + 1) // 2)
    counts: Counter[str] = Counter()
    for card in cards:
        section_data = card.get(section)
        if isinstance(section_data, dict):
            counts.update(ordered_present_fields(section_data, fields))
    return [field for field in fields if counts[field] >= threshold]


def _introduction_flow(cards: list[dict[str, Any]]) -> list[str]:
    order = (
        "opening_strategy",
        "problem_context",
        "literature_review_strategy",
        "research_gap",
        "theoretical_framework",
        "research_questions",
        "contribution_statement",
    )
    threshold = max(1, (len(cards) + 1) // 2)
    counts: Counter[str] = Counter()
    for card in cards:
        introduction = card.get("introduction", {})
        if not isinstance(introduction, dict):
            continue
        for field in order:
            value = introduction.get(field)
            if isinstance(value, dict):
                if any(item not in (None, False, "", []) for item in value.values()):
                    counts[field] += 1
            elif value not in (None, "", []):
                counts[field] += 1
    return [field for field in order if counts[field] >= threshold]


def aggregate(journal: str) -> dict[str, Any]:
    paths = card_files(journal)
    if not paths:
        raise ValueError(f"no paper cards found for journal: {journal}")
    cards = [load_yaml(path) for path in paths]
    invalid = [path for path, card in zip(paths, cards) if not isinstance(card, dict)]
    if invalid:
        raise ValueError(f"paper card is not a mapping: {invalid[0]}")
    mismatches = [path for path, card in zip(paths, cards) if _nested(card, "paper", "journal") != journal]
    if mismatches:
        raise ValueError(f"paper card journal mismatch: {mismatches[0]}")

    sample_size = len(cards)
    methodology_counts = Counter(_nested(card, "paper", "methodology") for card in cards)
    methodology_counts.pop(None, None)
    emphases: Counter[str] = Counter()
    for card in cards:
        features = card.get("writing_features", {})
        if not isinstance(features, dict):
            continue
        for field in (
            "theory_emphasis",
            "evidence_emphasis",
            "practical_implication_emphasis",
            "educational_implication_emphasis",
        ):
            value = features.get(field)
            if value:
                emphases[str(value)] += 1

    return {
        "pattern_type": "observed_pattern",
        "journal": {"id": journal},
        "sample": {"article_count": sample_size},
        "introduction": {
            "common_flow": _introduction_flow(cards),
            "research_gap": _observed_boolean(
                cards,
                ("introduction", "research_gap", "explicit"),
                position_path=("introduction", "research_gap", "position"),
                evidence_basis="semantic_analysis",
                unknown_as_absent=False,
            ),
            "theoretical_framework": _observed_boolean(
                cards,
                ("introduction", "theoretical_framework", "separate_section"),
                position_path=("introduction", "theoretical_framework", "position"),
                evidence_basis="explicit_separate_section",
                unknown_as_absent=True,
            ),
            "research_questions": _observed_boolean(
                cards,
                ("introduction", "research_questions", "present"),
                position_path=("introduction", "research_questions", "position"),
                evidence_basis="explicit_heading_or_question_list",
                unknown_as_absent=True,
            ),
        },
        "methods": {"common_flow": _common_flow(cards, "methods", METHOD_FIELDS)},
        "results": {"common_flow": _common_flow(cards, "results", RESULT_FIELDS)},
        "discussion": {"common_flow": _common_flow(cards, "discussion", DISCUSSION_FIELDS)},
        "methodology_distribution": [
            {
                "methodology": name,
                "evidence_count": count,
                "sample_size": sample_size,
                "frequency": round(count / sample_size, 2),
            }
            for name, count in sorted(methodology_counts.items())
        ],
        "journal_emphasis": [name for name, count in emphases.most_common() if count / sample_size >= 0.5],
        "evidence": {"source_type": "exemplar_analysis"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    output = (
        SKILL_ROOT / "patterns" / "journals" / f"{args.journal}.yaml"
        if args.output is None
        else SKILL_ROOT / args.output
    )
    dump_yaml(aggregate(args.journal), output)
    print(f"generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
