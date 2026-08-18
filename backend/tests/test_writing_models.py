import pytest

from stem_sci.agents.evidence_pipeline import PaperCard
from stem_sci.agents.writing_pipeline import (
    AtomicClaimGraph,
    AtomicClaimNode,
    ClaimRelation,
    WritingContextBundle,
    validate_claim_graph,
    validate_claim_node,
)
from stem_sci.context.models import EvidenceRef, SourceLocation, VerificationStatus
from stem_sci.core.claims import ClaimType


def evidence() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="evidence-1",
        project_id="physics-demo",
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="Verified.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=9),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def context() -> WritingContextBundle:
    return WritingContextBundle(
        project_id="physics-demo",
        approved_research_scope="AI-supported physics modeling",
        evidence_refs=[evidence()],
        paper_cards=[
            PaperCard(
                paper_card_id="card-1",
                project_id="physics-demo",
                source_ref="source-1",
                title="Verified paper",
                evidence_refs=["evidence-1"],
            )
        ],
        approved_study_protocol_refs=["protocol-1"],
        validated_result_cards=["result-1"],
        context_hash="a" * 64,
    )


def test_result_claim_requires_validated_result_ref() -> None:
    claim = AtomicClaimNode(
        project_id="physics-demo",
        claim_id="claim-1",
        text="结果显示……",
        claim_type=ClaimType.RESULT,
        section_target="results",
    )

    with pytest.raises(ValueError, match="validated result"):
        validate_claim_node(claim, context())


def test_literature_claim_requires_context_evidence() -> None:
    claim = AtomicClaimNode(
        project_id="physics-demo",
        claim_id="claim-1",
        text="The literature reports a bounded effect.",
        claim_type=ClaimType.LITERATURE,
        evidence_refs=["unknown-evidence"],
        section_target="introduction",
    )

    with pytest.raises(ValueError, match="evidence"):
        validate_claim_node(claim, context())


def test_graph_rejects_cross_project_claim_and_exposes_result_claims() -> None:
    graph = AtomicClaimGraph(
        project_id="physics-demo",
        nodes=[
            AtomicClaimNode(
                project_id="physics-demo",
                claim_id="result-claim",
                text="The validated result changed.",
                claim_type=ClaimType.RESULT,
                result_card_ref="result-1",
                section_target="results",
            ),
            AtomicClaimNode(
                project_id="other-project",
                claim_id="other-claim",
                text="Other project.",
                claim_type=ClaimType.LIMITATION,
                section_target="limitations",
            ),
        ],
    )

    with pytest.raises(ValueError, match="project"):
        validate_claim_graph(graph, context())
    assert len(graph.result_claims) == 1


def test_claim_relation_is_explicit_and_strict() -> None:
    node = AtomicClaimNode(
        project_id="physics-demo",
        claim_id="interpretation-1",
        text="This may explain the result.",
        claim_type=ClaimType.INTERPRETATION,
        result_card_ref="result-1",
        relations=[("result-1", ClaimRelation.INTERPRETS)],
        section_target="discussion",
    )

    assert node.relations[0][1] is ClaimRelation.INTERPRETS
