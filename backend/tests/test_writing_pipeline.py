from stem_sci.agents import AgentInput, PaperWritingAgent
from stem_sci.agents.evidence_pipeline import PaperCard
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
import pytest

from stem_sci.agents.writing_pipeline import (
    AtomicClaimGraph,
    AtomicClaimNode,
    BilingualConsistencyStatus,
    ClaimRelation,
    PaperWritingPipeline,
    WritingContextBundle,
    WritingSufficiencyStatus,
)
from stem_sci.agents.writing_pipeline.validators import validate_claim_graph
from stem_sci.core.claims import ClaimType
from stem_sci.context.models import EvidenceRef, SourceLocation, VerificationStatus


def context(*, with_results: bool = True) -> WritingContextBundle:
    evidence = EvidenceRef(
        evidence_id="evidence-1",
        project_id="physics-demo",
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="Verified literature evidence.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=29),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    return WritingContextBundle(
        project_id="physics-demo",
        approved_research_scope="AI-supported physics modeling",
        evidence_refs=[evidence],
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
        validated_result_cards=["result-1"] if with_results else [],
        context_hash="a" * 64,
    )


def agent_input() -> AgentInput:
    agent = PaperWritingAgent()
    return AgentInput(
        agent_run_id="writing-run-1",
        task_ref="physics-demo:draft_manuscript",
        context_bundle_ref="writing-context://physics-demo",
        allowed_tool_capabilities=[],
        allowed_output_types=list(agent.allowed_output_types),
        policy_version="policy-v1",
        prompt_template_version="paper-writing-v1",
    )


def responses(*, include_result: bool = True) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = [
        {
            "project_id": "physics-demo",
            "claim_id": "limitation-1",
            "text": "The bounded study has limitations.",
            "claim_type": "LIMITATION",
            "section_target": "limitations",
            "strength": "bounded",
        }
    ]
    if include_result:
        nodes.insert(
            0,
            {
                "project_id": "physics-demo",
                "claim_id": "result-claim-1",
                "text": "The validated result was positive.",
                "claim_type": "RESULT",
                "result_card_ref": "result-1",
                "section_target": "results",
                "strength": "associational",
            },
        )
    claim_ids = [node["claim_id"] for node in nodes]
    strengths = {str(node["claim_id"]): str(node["strength"]) for node in nodes}
    limitations = ["limitation-1"]
    return [
        {"graph": {"project_id": "physics-demo", "nodes": nodes}},
        {
            "outline": {
                "outline_id": "outline-1",
                "project_id": "physics-demo",
                "title": "AI-supported physics modeling",
                "section_claim_ids": {
                    "results": ["result-claim-1"] if include_result else [],
                    "limitations": limitations,
                },
            }
        },
        {
            "draft": {
                "project_id": "physics-demo",
                "language": "zh-CN",
                "sections": {"results": "结果为正向。", "limitations": "研究存在局限。"},
                "claim_ids": claim_ids,
                "citation_refs": ["evidence-1"],
                "numeric_literals": ["64"],
                "result_directions": {"result-claim-1": "positive"} if include_result else {},
                "claim_strengths": strengths,
                "limitation_claim_ids": limitations,
                "status": "CANDIDATE",
            }
        },
        {
            "draft": {
                "project_id": "physics-demo",
                "language": "en-US",
                "sections": {
                    "results": "The result was positive.",
                    "limitations": "The study has limitations.",
                },
                "claim_ids": claim_ids,
                "citation_refs": ["evidence-1"],
                "numeric_literals": ["64"],
                "result_directions": {"result-claim-1": "positive"} if include_result else {},
                "claim_strengths": strengths,
                "limitation_claim_ids": limitations,
                "status": "CANDIDATE",
            }
        },
    ]


def pipeline(fake_responses: list[dict[str, object]]) -> tuple[PaperWritingPipeline, FakeLLMProvider]:
    provider = FakeLLMProvider(fake_responses)
    return PaperWritingPipeline(generator=StructuredGenerator(provider), model="gpt-test"), provider


def test_writing_pipeline_uses_one_claim_graph_for_both_languages() -> None:
    writing, provider = pipeline(responses())

    package = writing.run(context(), agent_input())

    assert package.chinese.claim_ids == package.english.claim_ids
    assert package.chinese.claim_ids == [node.claim_id for node in package.claim_graph.nodes]
    assert package.chinese.citation_refs == package.english.citation_refs
    assert package.consistency.status is BilingualConsistencyStatus.PASS
    assert package.sufficiency.status is WritingSufficiencyStatus.READY
    assert len(package.generation_metadata_refs) == 4
    assert provider.call_count == 4


def test_writing_pipeline_never_invents_results() -> None:
    writing, _ = pipeline(responses(include_result=True))

    package = writing.run(context(with_results=False), agent_input())

    assert package.sufficiency.status is WritingSufficiencyStatus.INCOMPLETE
    assert not package.claim_graph.result_claims
    assert "INCOMPLETE_RESULT_INPUT" in package.risk_flags


def test_writing_pipeline_rejects_demo_evidence_for_formal_literature_claim() -> None:
    original = context()
    demo_context = original.model_copy(
        update={
            "evidence_refs": [
                original.evidence_refs[0].model_copy(
                    update={"verification_status": VerificationStatus.DEMO_SEED}
                )
            ]
        }
    )
    literal_claim = {
        "project_id": "physics-demo",
        "claim_id": "literature-claim-1",
        "text": "A literature claim.",
        "claim_type": "LITERATURE",
        "evidence_refs": ["evidence-1"],
        "section_target": "introduction",
    }
    response_set = responses()
    response_set[0] = {"graph": {"project_id": "physics-demo", "nodes": [literal_claim]}}
    writing, _ = pipeline(response_set)

    package = writing.run(demo_context, agent_input())

    assert package.claim_graph.nodes == []
    assert "INVALID_CLAIM_REFERENCE" in package.risk_flags


def test_interpretation_claim_requires_result_relation_boundary_and_human_approval() -> None:
    result = AtomicClaimNode(
        project_id="physics-demo",
        claim_id="result-1",
        text="The validated result differs by group.",
        claim_type=ClaimType.RESULT,
        result_card_ref="result-1",
        section_target="results",
    )
    interpretation = AtomicClaimNode(
        project_id="physics-demo",
        claim_id="interpretation-1",
        text="The result may reflect the proposed learning mechanism.",
        claim_type=ClaimType.INTERPRETATION,
        evidence_refs=["evidence-1"],
        interpretation_boundary_ref="boundary://physics-demo/1",
        human_approval_ref="approval://physics-demo/interpretation/1",
        relations=[("result-1", ClaimRelation.INTERPRETS)],
        section_target="discussion",
    )

    graph = AtomicClaimGraph(project_id="physics-demo", nodes=[result, interpretation])
    assert validate_claim_graph(graph, context()) is graph

    invalid = interpretation.model_copy(update={"relations": []})
    with pytest.raises(ValueError, match="must interpret a RESULT"):
        validate_claim_graph(
            AtomicClaimGraph(project_id="physics-demo", nodes=[result, invalid]), context()
        )


def test_writing_pipeline_does_not_render_an_invalid_claim_graph_as_valid_content() -> None:
    invalid_interpretation = {
        "project_id": "physics-demo",
        "claim_id": "interpretation-1",
        "text": "An unsupported interpretation.",
        "claim_type": "INTERPRETATION",
        "evidence_refs": ["evidence-1"],
        "interpretation_boundary_ref": "boundary://physics-demo/1",
        "human_approval_ref": "approval://physics-demo/interpretation/1",
        "relations": [["missing-result", "INTERPRETS"]],
        "section_target": "discussion",
    }
    response_set = responses()
    response_set[0] = {"graph": {"project_id": "physics-demo", "nodes": [invalid_interpretation]}}
    writing, _ = pipeline(response_set)

    package = writing.run(context(), agent_input())

    assert package.claim_graph.nodes == []
    assert "INVALID_CLAIM_GRAPH" in package.risk_flags


def test_writing_agent_capability_exposes_bilingual_outputs() -> None:
    output_types = set(PaperWritingAgent.capability().allowed_output_types)

    assert {
        "AtomicClaimGraph",
        "ManuscriptDraftZh",
        "ManuscriptDraftEn",
        "BilingualConsistencyReport",
    } <= output_types


def test_writing_agent_adapts_package_to_candidate_artifacts() -> None:
    writing, _ = pipeline(responses())
    agent = PaperWritingAgent(pipeline=writing)

    result = agent.run_pipeline(agent_input(), context())

    assert result.agent_id == "paper_writing"
    assert len(result.llm_metadata_refs) == 4
    assert any("ManuscriptDraftZh" in ref for ref in result.candidate_artifact_refs)
    assert any("ManuscriptDraftEn" in ref for ref in result.candidate_artifact_refs)


def test_writing_agent_deterministic_fallback_produces_no_result_numbers() -> None:
    result = PaperWritingAgent().run_with_context(agent_input(), context())

    artifact_types = {artifact.artifact_type for artifact in result.candidate_artifacts}
    assert {"AtomicClaimGraph", "ManuscriptOutline", "WritingSufficiencyReport"} <= artifact_types
    assert "WRITING_PIPELINE_NOT_CONFIGURED" in result.risk_flags
    chinese = next(
        artifact.body for artifact in result.candidate_artifacts
        if artifact.artifact_type == "ManuscriptDraftZh"
    )
    assert chinese["numeric_literals"] == []
    assert chinese["status"] == "INCOMPLETE_CANDIDATE"


def test_writing_agent_falls_back_when_model_generation_fails() -> None:
    failing = PaperWritingPipeline(
        generator=StructuredGenerator(FakeLLMProvider([]), max_retries=0), model="gpt-test"
    )

    result = PaperWritingAgent(pipeline=failing).run_with_context(agent_input(), context())

    assert "MODEL_GENERATION_FAILED" in result.risk_flags
    assert "ManuscriptOutline" in {item.artifact_type for item in result.candidate_artifacts}
