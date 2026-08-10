from stem_sci.agents.writing_pipeline import (
    AtomicClaimGraph,
    AtomicClaimNode,
    BilingualConsistencyStatus,
    ManuscriptDraft,
    compare_bilingual_drafts,
)
from stem_sci.core.claims import ClaimType


def graph() -> AtomicClaimGraph:
    return AtomicClaimGraph(
        project_id="physics-demo",
        nodes=[
            AtomicClaimNode(
                project_id="physics-demo",
                claim_id="claim-1",
                text="The bounded result has limitations.",
                claim_type=ClaimType.LIMITATION,
                section_target="limitations",
                strength="associational",
            )
        ],
    )


def draft(
    language: str,
    body: str,
    *,
    numbers: list[str],
    result_direction: str = "positive",
    strength: str = "associational",
) -> ManuscriptDraft:
    return ManuscriptDraft(
        project_id="physics-demo",
        language=language,
        sections={"results": body},
        claim_ids=["claim-1"],
        citation_refs=["evidence-1"],
        numeric_literals=numbers,
        result_directions={"claim-1": result_direction},
        claim_strengths={"claim-1": strength},
        limitation_claim_ids=["claim-1"],
        status="CANDIDATE",
    )


def test_bilingual_report_blocks_numeric_mismatch() -> None:
    report = compare_bilingual_drafts(
        draft("zh-CN", "样本量 n=64", numbers=["64"]),
        draft("en-US", "The sample was n=65", numbers=["65"]),
        graph(),
    )

    assert report.status is BilingualConsistencyStatus.BLOCKED
    assert "BILINGUAL_MISMATCH" in report.risk_flags


def test_bilingual_report_passes_matching_claims_citations_and_numbers() -> None:
    report = compare_bilingual_drafts(
        draft("zh-CN", "样本量 n=64", numbers=["64"]),
        draft("en-US", "The sample was n=64", numbers=["64"]),
        graph(),
    )

    assert report.status is BilingualConsistencyStatus.PASS
    assert report.risk_flags == []


def test_bilingual_report_blocks_direction_strength_and_limitation_mismatch() -> None:
    chinese = draft("zh-CN", "结果存在局限。", numbers=["64"])
    english = draft(
        "en-US",
        "The result has limitations.",
        numbers=["64"],
        result_direction="negative",
        strength="causal",
    ).model_copy(update={"limitation_claim_ids": []})

    report = compare_bilingual_drafts(chinese, english, graph())

    assert report.status is BilingualConsistencyStatus.BLOCKED
    assert {
        "BILINGUAL_DIRECTION_MISMATCH",
        "BILINGUAL_STRENGTH_MISMATCH",
        "BILINGUAL_LIMITATION_MISMATCH",
    } <= set(report.risk_flags)


def test_bilingual_numeric_comparison_ignores_language_order() -> None:
    report = compare_bilingual_drafts(
        draft("zh-CN", "n=64, p=.05", numbers=["64", ".05"]),
        draft("en-US", "p=.05, n=64", numbers=[".05", "64"]),
        graph(),
    )

    assert report.status is BilingualConsistencyStatus.PASS
