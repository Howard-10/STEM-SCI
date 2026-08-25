"""Deterministic consistency checks for Chinese and English drafts."""

from __future__ import annotations

import re

from stem_sci.core.claims import ClaimType

from .models import (
    AtomicClaimGraph,
    BilingualConsistencyReport,
    BilingualConsistencyStatus,
    ManuscriptDraft,
)

NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?")


def compare_bilingual_drafts(
    chinese: ManuscriptDraft,
    english: ManuscriptDraft,
    graph: AtomicClaimGraph,
) -> BilingualConsistencyReport:
    risks: list[str] = []
    findings: list[str] = []
    if chinese.project_id != english.project_id or chinese.project_id != graph.project_id:
        risks.append("BILINGUAL_PROJECT_MISMATCH")
        findings.append("Chinese, English, and claim graph projects differ.")
    if set(chinese.claim_ids) != set(english.claim_ids):
        risks.append("BILINGUAL_CLAIM_MISMATCH")
        findings.append("Chinese and English claim IDs differ.")
    graph_claim_ids = {node.claim_id for node in graph.nodes}
    if set(chinese.claim_ids) != graph_claim_ids or set(english.claim_ids) != graph_claim_ids:
        risks.append("BILINGUAL_GRAPH_MISMATCH")
        findings.append("Draft claim IDs do not match the AtomicClaimGraph.")
    if set(chinese.citation_refs) != set(english.citation_refs):
        risks.append("BILINGUAL_CITATION_MISMATCH")
        findings.append("Chinese and English citation references differ.")
    chinese_numbers = chinese.numeric_literals or _numbers(chinese.sections)
    english_numbers = english.numeric_literals or _numbers(english.sections)
    if sorted(chinese_numbers) != sorted(english_numbers):
        risks.append("BILINGUAL_MISMATCH")
        findings.append("Chinese and English numeric literals differ.")
    if chinese.result_directions != english.result_directions:
        risks.append("BILINGUAL_DIRECTION_MISMATCH")
        findings.append("Chinese and English result directions differ.")
    graph_strengths = {node.claim_id: node.strength for node in graph.nodes}
    if (
        chinese.claim_strengths != english.claim_strengths
        or chinese.claim_strengths != graph_strengths
    ):
        risks.append("BILINGUAL_STRENGTH_MISMATCH")
        findings.append("Draft claim strengths differ from each other or the claim graph.")
    graph_limitations = {
        node.claim_id for node in graph.nodes if node.claim_type is ClaimType.LIMITATION
    }
    if (
        set(chinese.limitation_claim_ids) != set(english.limitation_claim_ids)
        or set(chinese.limitation_claim_ids) != graph_limitations
    ):
        risks.append("BILINGUAL_LIMITATION_MISMATCH")
        findings.append("Draft limitation coverage differs from the claim graph.")
    status = BilingualConsistencyStatus.BLOCKED if risks else BilingualConsistencyStatus.PASS
    return BilingualConsistencyReport(
        report_id=f"bilingual-{graph.project_id}",
        project_id=graph.project_id,
        status=status,
        risk_flags=risks,
        findings=findings,
    )


def _numbers(sections: dict[str, str]) -> list[str]:
    return NUMBER_PATTERN.findall(" ".join(sections.values()))
