from stem_sci.agents import AgentInput
from stem_sci.agents.evidence_pipeline import (
    EvidenceReviewContext,
    EvidenceReviewPipeline,
    PackageStatus,
)
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator
from stem_sci.agents.writing_pipeline import PaperWritingPipeline, WritingContextBundle
from stem_sci.context.models import EvidenceRef, SourceLocation, VerificationStatus


def _agent_input(project_id: str, task: str, output_types: list[str]) -> AgentInput:
    return AgentInput(
        agent_run_id=f"run-{task}",
        task_ref=f"{project_id}:{task}",
        context_bundle_ref=f"context://{project_id}/{task}",
        allowed_tool_capabilities=[],
        allowed_output_types=output_types,
        policy_version="policy-v1",
        prompt_template_version="test-v1",
    )


def test_fake_gpt_runs_evidence_then_bilingual_writing() -> None:
    project_id = "fake-agent-e2e"
    evidence = EvidenceRef(
        evidence_id="evidence-1",
        project_id=project_id,
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="Verified evidence.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=18),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    responses: list[dict[str, object]] = [
        {
            "cards": [
                {
                    "paper_card_id": "card-1",
                    "project_id": project_id,
                    "source_ref": "source-1",
                    "title": "Verified paper",
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "rows": [
                {
                    "row_id": "row-1",
                    "project_id": project_id,
                    "research_question": "Does it work?",
                    "source_ref": "source-1",
                    "relation": "SUPPORTING",
                    "finding": "The bounded evidence supports the intervention.",
                    "evidence_refs": ["evidence-1"],
                }
            ]
        },
        {
            "conflict_map": {"map_id": "conflicts-1", "project_id": project_id, "conflicts": []},
            "gap_report": {
                "report_id": "gaps-1",
                "project_id": project_id,
                "gaps": [],
                "limit_text": "在当前限定语料中未发现冲突研究。",
            },
        },
        {
            "synthesis": {
                "synthesis_id": "synthesis-1",
                "project_id": project_id,
                "summary": "Bounded evidence synthesis.",
                "evidence_refs": ["evidence-1"],
                "corpus_limit": "Only verified local evidence was used.",
            }
        },
        {
            "graph": {
                "project_id": project_id,
                "nodes": [
                    {
                        "project_id": project_id,
                        "claim_id": "result-1",
                        "text": "The validated result was positive.",
                        "claim_type": "RESULT",
                        "result_card_ref": "validated-result-1",
                        "section_target": "results",
                        "strength": "associational",
                    },
                    {
                        "project_id": project_id,
                        "claim_id": "limitation-1",
                        "text": "The bounded study has limitations.",
                        "claim_type": "LIMITATION",
                        "section_target": "limitations",
                        "strength": "bounded",
                    },
                ],
            }
        },
        {
            "outline": {
                "outline_id": "outline-1",
                "project_id": project_id,
                "title": "AI-supported physics modeling",
                "section_claim_ids": {"results": ["result-1"], "limitations": ["limitation-1"]},
            }
        },
        {
            "draft": {
                "project_id": project_id,
                "language": "zh-CN",
                "sections": {"results": "结果为正向。", "limitations": "研究存在局限。"},
                "claim_ids": ["result-1", "limitation-1"],
                "citation_refs": ["evidence-1"],
                "numeric_literals": [],
                "result_directions": {"result-1": "positive"},
                "claim_strengths": {"result-1": "associational", "limitation-1": "bounded"},
                "limitation_claim_ids": ["limitation-1"],
                "status": "CANDIDATE",
            }
        },
        {
            "draft": {
                "project_id": project_id,
                "language": "en-US",
                "sections": {"results": "The result was positive.", "limitations": "The study has limitations."},
                "claim_ids": ["result-1", "limitation-1"],
                "citation_refs": ["evidence-1"],
                "numeric_literals": [],
                "result_directions": {"result-1": "positive"},
                "claim_strengths": {"result-1": "associational", "limitation-1": "bounded"},
                "limitation_claim_ids": ["limitation-1"],
                "status": "CANDIDATE",
            }
        },
    ]
    provider = FakeLLMProvider(responses)
    generator = StructuredGenerator(provider)
    evidence_package = EvidenceReviewPipeline(generator=generator, model="gpt-test").run(
        EvidenceReviewContext(
            project_id=project_id,
            context_bundle_ref=f"context://{project_id}/evidence",
            research_scope="AI-supported physics modeling",
            evidence_refs=[evidence],
            source_refs=["source-1"],
            context_hash="a" * 64,
        ),
        _agent_input(project_id, "evidence", ["BoundedEvidenceSynthesis"]),
    )

    assert evidence_package.status is PackageStatus.READY
    writing_package = PaperWritingPipeline(generator=generator, model="gpt-test").run(
        WritingContextBundle(
            project_id=project_id,
            approved_research_scope="AI-supported physics modeling",
            evidence_refs=[evidence],
            paper_cards=evidence_package.paper_cards,
            evidence_matrix=[
                row.model_dump(mode="json") for row in evidence_package.evidence_matrix
            ],
            approved_study_protocol_refs=["protocol-1"],
            validated_result_cards=["validated-result-1"],
            context_hash="b" * 64,
        ),
        _agent_input(project_id, "writing", ["ManuscriptDraftZh", "ManuscriptDraftEn"]),
    )

    assert writing_package.consistency.status.value == "PASS"
    assert provider.call_count == 8
