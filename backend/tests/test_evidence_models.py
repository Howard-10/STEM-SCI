import pytest
from pydantic import ValidationError

from stem_sci.agents.evidence_pipeline import (
    BoundedEvidenceSynthesis,
    EvidenceReviewContext,
    EvidenceReviewPackage,
    EvidenceSufficiencyReport,
    PackageStatus,
    PaperCard,
    ResearchGapReport,
    ScreeningDecision,
    ScreeningStatus,
    validate_evidence_context,
)
from stem_sci.context.models import EvidenceRef, SourceLocation, VerificationStatus


def evidence_ref(
    evidence_id: str = "evidence-1",
    *,
    project_id: str = "physics-demo",
    status: VerificationStatus = VerificationStatus.SOURCE_VERIFIED,
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        project_id=project_id,
        source_id=f"source-{evidence_id}",
        chunk_id=f"chunk-{evidence_id}",
        excerpt="Verified source text.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=21),
        verification_status=status,
    )


def make_context(*refs: EvidenceRef) -> EvidenceReviewContext:
    return EvidenceReviewContext(
        project_id="physics-demo",
        context_bundle_ref="context://physics-demo/evidence",
        research_scope="AI-supported physics modeling",
        evidence_refs=list(refs),
        source_refs=[ref.source_id for ref in refs],
        context_hash="a" * 64,
    )


def test_evidence_context_rejects_unverified_evidence() -> None:
    context = make_context(
        evidence_ref(status=VerificationStatus.MODEL_GENERATED_UNVERIFIED)
    )

    with pytest.raises(ValueError, match="verified"):
        validate_evidence_context(context)


def test_evidence_context_rejects_cross_project_evidence() -> None:
    context = make_context(evidence_ref(project_id="other-project"))

    with pytest.raises(ValueError, match="project"):
        validate_evidence_context(context)


def test_evidence_models_are_strict_and_reference_backed() -> None:
    with pytest.raises(ValidationError):
        ScreeningDecision(
            source_ref="source-1",
            decision=ScreeningStatus.INCLUDE,
            reason="Relevant",
            evidence_refs=["evidence-1"],
            unexpected="rejected",
        )

    with pytest.raises(ValidationError):
        PaperCard(
            paper_card_id="card-1",
            project_id="physics-demo",
            source_ref="source-1",
            title="Paper",
            evidence_refs=[],
        )


def test_evidence_review_package_tracks_typed_outputs_and_metadata() -> None:
    context = make_context(evidence_ref())
    package = EvidenceReviewPackage(
        project_id=context.project_id,
        status=PackageStatus.READY,
        paper_cards=[
            PaperCard(
                paper_card_id="card-1",
                project_id="physics-demo",
                source_ref="source-evidence-1",
                title="Paper",
                evidence_refs=["evidence-1"],
            )
        ],
        research_gap_report=ResearchGapReport(
            report_id="gap-1",
            project_id="physics-demo",
            gaps=[],
            limit_text="在当前限定语料中未发现相关研究。",
        ),
        synthesis=BoundedEvidenceSynthesis(
            synthesis_id="synthesis-1",
            project_id="physics-demo",
            summary="Bounded synthesis.",
            evidence_refs=["evidence-1"],
            corpus_limit="Only the verified local corpus was used.",
        ),
        sufficiency=EvidenceSufficiencyReport(
            report_id="sufficiency-1",
            project_id="physics-demo",
            status=PackageStatus.READY,
            evidence_count=1,
        ),
        used_evidence_refs=["evidence-1"],
        generation_metadata_refs=["llm-metadata://request-1"],
    )

    assert package.used_evidence_refs == ["evidence-1"]
    assert package.status is PackageStatus.READY
