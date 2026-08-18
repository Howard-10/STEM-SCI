from datetime import UTC, datetime

from stem_sci.agents import AgentInput, EvidenceReviewAgent
from stem_sci.agents.evidence_pipeline import (
    EvidenceReviewContext,
    EvidenceReviewPipeline,
    PackageStatus,
    ScreeningStatus,
)
from stem_sci.agents.evidence_pipeline.stages import audit_corpus, screen_sources
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus


def verified_ref(evidence_id: str = "evidence-1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        project_id="physics-demo",
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="The intervention improved transfer performance.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=47),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )


def review_context(*refs: EvidenceRef) -> EvidenceReviewContext:
    return EvidenceReviewContext(
        project_id="physics-demo",
        context_bundle_ref="context://physics-demo/evidence",
        research_scope="AI-supported physics modeling",
        evidence_refs=list(refs),
        source_refs=sorted({ref.source_id for ref in refs}),
        context_hash="a" * 64,
    )


def agent_input() -> AgentInput:
    agent = EvidenceReviewAgent()
    return AgentInput(
        agent_run_id="evidence-run-1",
        task_ref="physics-demo:synthesize_evidence",
        context_bundle_ref="context://physics-demo/evidence",
        allowed_tool_capabilities=[],
        allowed_output_types=list(agent.allowed_output_types),
        policy_version="policy-v1",
        prompt_template_version="evidence-review-v1",
    )


def valid_responses(*, synthesis_refs: list[str] | None = None) -> list[dict[str, object]]:
    return [
        {
            "cards": [
                {
                    "paper_card_id": "card-1",
                    "project_id": "physics-demo",
                    "source_ref": "source-1",
                    "title": "Verified paper",
                    "main_findings": ["Transfer performance improved."],
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "rows": [
                {
                    "row_id": "row-1",
                    "project_id": "physics-demo",
                    "research_question": "Does the intervention support transfer?",
                    "source_ref": "source-1",
                    "relation": "SUPPORTING",
                    "finding": "Transfer performance improved.",
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "conflict_map": {
                "map_id": "conflicts-1",
                "project_id": "physics-demo",
                "conflicts": [],
            },
            "gap_report": {
                "report_id": "gaps-1",
                "project_id": "physics-demo",
                "gaps": [],
                "limit_text": "No research exists on this topic.",
            },
        },
        {
            "synthesis": {
                "synthesis_id": "synthesis-1",
                "project_id": "physics-demo",
                "summary": "The bounded corpus reports improved transfer.",
                "evidence_refs": synthesis_refs or ["evidence-1"],
                "corpus_limit": "Only the verified local corpus was used.",
            }
        },
    ]


def make_pipeline(responses: list[dict[str, object]]) -> tuple[EvidenceReviewPipeline, FakeLLMProvider]:
    provider = FakeLLMProvider(responses)
    return (
        EvidenceReviewPipeline(
            generator=StructuredGenerator(provider),
            model="gpt-test",
        ),
        provider,
    )


def test_evidence_pipeline_marks_gap_as_corpus_limited() -> None:
    pipeline, provider = make_pipeline(valid_responses())

    package = pipeline.run(review_context(verified_ref()), agent_input())

    assert package.status is PackageStatus.READY
    assert package.research_gap_report is not None
    assert package.research_gap_report.limit_text.startswith("在当前限定语料中")
    assert package.used_evidence_refs == ["evidence-1"]
    assert len(package.generation_metadata_refs) == 4
    assert provider.call_count == 4


def test_evidence_pipeline_drops_synthesis_with_unknown_reference() -> None:
    pipeline, _ = make_pipeline(valid_responses(synthesis_refs=["unknown-evidence"]))

    package = pipeline.run(review_context(verified_ref()), agent_input())

    assert package.synthesis is None
    assert package.status is PackageStatus.INCOMPLETE
    assert "INVALID_EVIDENCE_REFERENCE" in package.risk_flags
    assert package.used_evidence_refs == ["evidence-1"]


def test_evidence_pipeline_is_incomplete_without_valid_paper_cards() -> None:
    invalid = valid_responses()
    invalid[0] = {
        "cards": [
            {
                "paper_card_id": "card-invalid",
                "project_id": "physics-demo",
                "source_ref": "unknown-source",
                "title": "Untraceable paper",
                "evidence_refs": ["evidence-1"],
            }
        ]
    }
    pipeline, _ = make_pipeline(invalid)

    package = pipeline.run(review_context(verified_ref()), agent_input())

    assert package.status is PackageStatus.INCOMPLETE
    assert "NO_VALID_PAPER_CARDS" in package.risk_flags
    assert "valid_paper_cards" in package.sufficiency.missing_requirements


def test_evidence_pipeline_short_circuits_when_no_verified_evidence() -> None:
    pipeline, provider = make_pipeline([])

    package = pipeline.run(review_context(), agent_input())

    assert package.status is PackageStatus.INCOMPLETE
    assert package.synthesis is None
    assert package.sufficiency.evidence_count == 0
    assert "INSUFFICIENT_CORPUS_COVERAGE" in package.risk_flags
    assert provider.call_count == 0


def test_formal_evidence_review_rejects_demo_seed_but_demo_review_allows_it() -> None:
    import pytest

    demo = verified_ref().model_copy(update={"verification_status": VerificationStatus.DEMO_SEED})
    pipeline, _ = make_pipeline(valid_responses())

    with pytest.raises(ValueError, match="formal evidence review"):
        pipeline.run(review_context(demo), agent_input())

    package = pipeline.run(
        review_context(demo).model_copy(update={"intended_use": "demo"}), agent_input()
    )
    assert package.status is PackageStatus.READY


def test_screening_uncertain_source_does_not_invent_evidence_reference() -> None:
    context = review_context(verified_ref()).model_copy(
        update={"source_refs": ["source-1", "source-without-evidence"]}
    )

    decisions = screen_sources(context, audit_corpus(context))
    uncertain = next(item for item in decisions if item.source_ref == "source-without-evidence")

    assert uncertain.decision is ScreeningStatus.UNCERTAIN
    assert uncertain.evidence_refs == []


def test_evidence_agent_capability_lists_pipeline_outputs() -> None:
    capability = EvidenceReviewAgent.capability()

    assert "BoundedEvidenceSynthesis" in capability.allowed_output_types
    assert "EvidenceSufficiencyReport" in capability.allowed_output_types
    assert "CorpusCoverageReport" in capability.allowed_output_types


def test_evidence_agent_deterministic_fallback_produces_traceable_candidates() -> None:
    evidence = verified_ref()
    context_bundle = ContextBundle(
        context_id="context-1",
        project_id="physics-demo",
        task_ref="physics-demo:evidence",
        query="AI-supported physics modeling",
        evidence_refs=[evidence],
        source_refs=[evidence.source_id],
        verification_summary={"source_verified": 1},
        token_budget=500,
        estimated_tokens=20,
        context_hash="a" * 64,
        generated_at="2026-08-11T00:00:00Z",
    )

    result = EvidenceReviewAgent().run_with_context(agent_input(), context_bundle)

    artifact_types = {artifact.artifact_type for artifact in result.candidate_artifacts}
    assert {"PaperCardCollection", "EvidenceMatrixCandidate", "ScreeningLedger"} <= artifact_types
    matrix = next(
        artifact.body for artifact in result.candidate_artifacts
        if artifact.artifact_type == "EvidenceMatrixCandidate"
    )
    assert matrix["rows"][0]["relation"] == "MENTIONING"
    assert "MODEL_SYNTHESIS_NOT_CONFIGURED" in result.risk_flags


def test_evidence_agent_falls_back_when_model_generation_fails() -> None:
    evidence = verified_ref()
    context_bundle = ContextBundle(
        context_id="context-failure-1",
        project_id="physics-demo",
        task_ref="physics-demo:evidence",
        query="AI-supported physics modeling",
        evidence_refs=[evidence],
        source_refs=[evidence.source_id],
        verification_summary={"source_verified": 1},
        token_budget=500,
        estimated_tokens=20,
        context_hash="a" * 64,
        generated_at="2026-08-11T00:00:00Z",
    )
    failing = EvidenceReviewPipeline(
        generator=StructuredGenerator(FakeLLMProvider([]), max_retries=0), model="gpt-test"
    )

    result = EvidenceReviewAgent(pipeline=failing).run_with_context(agent_input(), context_bundle)

    assert "MODEL_GENERATION_FAILED" in result.risk_flags
    assert "PaperCardCollection" in {item.artifact_type for item in result.candidate_artifacts}


def test_pipeline_result_can_be_adapted_to_agent_result() -> None:
    pipeline, _ = make_pipeline(valid_responses())
    agent = EvidenceReviewAgent(pipeline=pipeline)

    result = agent.run_pipeline(agent_input(), review_context(verified_ref()))

    assert result.agent_id == "evidence_review"
    assert result.evidence_refs == ["evidence-1"]
    assert any("BoundedEvidenceSynthesis" in ref for ref in result.candidate_artifact_refs)
    assert result.created_at <= datetime.now(UTC)
