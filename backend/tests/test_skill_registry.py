from __future__ import annotations

import pytest

from stem_sci.skills.builtin import BUILTIN_SKILLS
from stem_sci.skills.models import RiskLevel, SkillManifest
from stem_sci.skills.registry import SkillRegistry
from stem_sci.skills.resolver import SkillResolver
from stem_sci.tools import ToolExecutionMode, ToolRegistry, ToolSpec


def skill_manifest(
    skill_id: str,
    version: str = "v1",
    *,
    agents: list[str] | None = None,
    tasks: list[str] | None = None,
    tools: list[str] | None = None,
) -> SkillManifest:
    return SkillManifest(
        skill_id=skill_id,
        skill_version=version,
        agent_ids=agents or ["evidence_review"],
        supported_task_types=tasks or ["synthesize_evidence"],
        required_tool_ids=tools or ["context_bundle_read"],
        input_schema_refs=["schema://Input"],
        output_schema_refs=["schema://Output"],
        prompt_template_refs=["prompt://skill-v1"],
        validator_refs=["validator://skill"],
        risk_level=RiskLevel.LOW,
    )


def tool_spec(tool_id: str, version: str = "v1") -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        tool_version=version,
        capability=tool_id,
        execution_mode=ToolExecutionMode.READ_ONLY,
        input_schema_ref="schema://Input",
        output_schema_ref="schema://Output",
        timeout_seconds=10,
    )


def test_skill_registry_rejects_duplicate_version() -> None:
    registry = SkillRegistry([skill_manifest("bounded_corpus_review")])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(skill_manifest("bounded_corpus_review"))


def test_skill_registry_filters_agent_and_task_and_sorts() -> None:
    registry = SkillRegistry(
        [
            skill_manifest("zeta", agents=["evidence_review"], tasks=["synthesize_evidence"]),
            skill_manifest("alpha", agents=["evidence_review"], tasks=["synthesize_evidence"]),
            skill_manifest("other", agents=["paper_writing"], tasks=["draft_manuscript"]),
        ]
    )

    assert [item.skill_id for item in registry.list_for_agent("evidence_review", "synthesize_evidence")] == [
        "alpha",
        "zeta",
    ]


def test_skill_resolver_filters_agent_and_task() -> None:
    tool_registry = ToolRegistry([tool_spec("context_bundle_read")])
    skill_registry = SkillRegistry(
        [
            skill_manifest("bounded_corpus_review"),
            skill_manifest(
                "draft_manuscript",
                agents=["paper_writing"],
                tasks=["draft_manuscript"],
            ),
        ]
    )
    resolver = SkillResolver(skill_registry, tool_registry)

    resolved = resolver.resolve_for_agent(
        agent_id="evidence_review",
        task_type="synthesize_evidence",
        allowed_skill_refs=["draft_manuscript@v1", "bounded_corpus_review@v1"],
    )

    assert resolved.skill_id == "bounded_corpus_review"


def test_builtin_manifests_cover_the_required_six_agent_bindings() -> None:
    refs_by_agent = {
        agent_id: {
            f"{manifest.skill_id}@{manifest.skill_version}"
            for manifest in BUILTIN_SKILLS
            if agent_id in manifest.agent_ids
        }
        for agent_id in (
            "mentor_planning",
            "evidence_review",
            "research_design",
            "data_analysis",
            "paper_writing",
            "independent_review",
        )
    }

    assert refs_by_agent == {
        "mentor_planning": {
            "research_scope_planning@v1",
            "research_feasibility_assessment@v1",
        },
        "evidence_review": {
            "bounded_corpus_review@v1",
            "source_screening@v1",
            "citation_grounding@v1",
        },
        "research_design": {
            "research_question_formulation@v1",
            "protocol_draft_validation@v1",
        },
        "data_analysis": {
            "data_readiness_audit@v1",
            "statistical_analysis_execution@v1",
            "result_card_generation@v1",
        },
        "paper_writing": {
            "atomic_claim_graph_construction@v1",
            "bilingual_manuscript_rendering@v1",
        },
        "independent_review": {
            "citation_review@v1",
            "methodology_review@v1",
            "reproducibility_review@v1",
        },
    }


def test_skill_resolver_rejects_unapproved_tool_binding() -> None:
    skill_registry = SkillRegistry(
        [skill_manifest("bad-skill", tools=["not_registered"])]
    )
    tool_registry = ToolRegistry([tool_spec("context_bundle_read")])
    with pytest.raises(ValueError, match="tool not registered"):
        SkillResolver(skill_registry, tool_registry).resolve_for_agent(
            "evidence_review", "synthesize_evidence", ["bad-skill@v1"]
        )


@pytest.mark.parametrize(
    ("agent_id", "task_type", "ref", "message"),
    [
        ("paper_writing", "synthesize_evidence", "bounded_corpus_review@v1", "agent"),
        ("evidence_review", "draft_manuscript", "bounded_corpus_review@v1", "task"),
        ("evidence_review", "synthesize_evidence", "unknown@v1", "unknown skill"),
    ],
)
def test_skill_resolver_rejects_invalid_context(
    agent_id: str, task_type: str, ref: str, message: str
) -> None:
    resolver = SkillResolver(
        SkillRegistry([skill_manifest("bounded_corpus_review")]),
        ToolRegistry([tool_spec("context_bundle_read")]),
    )
    with pytest.raises(ValueError, match=message):
        resolver.resolve_for_agent(agent_id, task_type, [ref])
