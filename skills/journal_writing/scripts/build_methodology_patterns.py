#!/usr/bin/env python3
"""Build methodology patterns and append evidence counts from all paper cards."""

from __future__ import annotations

from collections import Counter
from typing import Any

from _pattern_utils import (
    SKILL_ROOT,
    canonical_methodology,
    card_files,
    dump_yaml,
    load_yaml,
)

BASE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "quantitative": {
        "methods": ["research_design", "participants", "instruments", "validity_reliability", "data_collection", "statistical_analysis"],
        "results": ["descriptive_statistics", "inferential_statistics", "effect_or_relationship"],
        "discussion": ["interpret_main_results", "connect_with_prior_research", "theoretical_interpretation", "educational_implications", "limitations"],
    },
    "qualitative": {
        "methods": ["research_design", "participants", "sampling", "data_collection", "coding", "qualitative_analysis", "trustworthiness"],
        "results": ["theme", "supporting_evidence", "interpretation"],
        "discussion": ["interpret_major_themes", "connect_with_prior_research", "theoretical_interpretation", "educational_implications", "limitations"],
    },
    "mixed_methods": {
        "methods": ["mixed_methods_design", "quantitative_strand", "qualitative_strand", "strand_sequence_or_priority", "integration_strategy", "validity_reliability_and_trustworthiness"],
        "results": ["quantitative_findings", "qualitative_findings", "integrated_meta_inference"],
        "discussion": ["interpret_convergent_or_divergent_findings", "explain_cross_strand_integration", "connect_with_prior_research", "educational_implications", "limitations"],
    },
    "experiment": {
        "methods": ["experimental_design", "participants_and_assignment", "intervention_and_comparator", "outcome_measures", "fidelity_and_controls", "statistical_analysis"],
        "results": ["baseline_equivalence", "intervention_effect", "uncertainty_and_effect_size", "robustness_or_sensitivity_analysis"],
        "discussion": ["interpret_intervention_effect", "discuss_causal_scope", "connect_with_prior_research", "educational_implications", "limitations"],
    },
    "instrument_development": {
        "methods": ["construct_definition", "item_generation", "expert_review_or_content_validity", "pilot_sample", "factor_or_item_analysis", "reliability_and_validity_evidence"],
        "results": ["item_reduction", "dimensionality", "reliability_evidence", "validity_evidence", "final_instrument"],
        "discussion": ["interpret_measurement_evidence", "compare_existing_instruments", "intended_uses", "limitations", "future_validation"],
    },
}


def _methodology_counts() -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    cards = card_files()
    for path in cards:
        card = load_yaml(path)
        if not isinstance(card, dict):
            continue
        paper = card.get("paper")
        raw = paper.get("methodology") if isinstance(paper, dict) else None
        methodology = canonical_methodology(raw)
        if methodology:
            counts[methodology] += 1
    return counts, len(cards)


def build() -> list[Any]:
    counts, total_cards = _methodology_counts()
    outputs = []
    target = SKILL_ROOT / "patterns" / "methodology"
    for methodology, sections in BASE_PATTERNS.items():
        data: dict[str, Any] = {
            "pattern_type": "methodology_pattern",
            "methodology": methodology,
            "methods": {"common_flow": sections["methods"]},
            "results": {"common_flow": sections["results"]},
            "discussion": {"common_flow": sections["discussion"]},
            "observed_sample": {
                "matching_article_count": counts[methodology],
                "total_card_count": total_cards,
                "frequency": round(counts[methodology] / total_cards, 2) if total_cards else None,
            },
        }
        output = target / f"{methodology}.yaml"
        dump_yaml(data, output)
        outputs.append(output)
    return outputs


def main() -> int:
    for output in build():
        print(f"generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
