from stem_sci.agents import AgentInput, PaperWritingAgent
from stem_sci.agents.evidence_pipeline import PaperCard
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
from stem_sci.agents.writing_pipeline import (
    BilingualConsistencyStatus,
    PaperWritingPipeline,
    WritingContextBundle,
    WritingSufficiencyStatus,
)
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
