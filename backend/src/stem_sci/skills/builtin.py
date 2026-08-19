"""Initial versioned Skill bindings for the six Phase 1 Agent families.

The manifests are deliberately declarative.  They do not execute a Tool or
grant workflow authority; the Controller resolves them against its Tool
registry before dispatch.
"""

from __future__ import annotations

from .models import RiskLevel, SkillManifest


def _manifest(
    skill_id: str,
    agent_id: str,
    tasks: list[str],
    tool_ids: list[str],
    output_schema: str,
    *,
    risk: RiskLevel = RiskLevel.LOW,
) -> SkillManifest:
    return SkillManifest(
        skill_id=skill_id,
        skill_version="v1",
        agent_ids=[agent_id],
        supported_task_types=tasks,
        required_tool_ids=tool_ids,
        input_schema_refs=["schema://AgentInput"],
        output_schema_refs=[output_schema],
        prompt_template_refs=[f"prompt://{skill_id}-v1"],
        validator_refs=[f"validator://{skill_id}"],
        risk_level=risk,
    )


BUILTIN_SKILLS: tuple[SkillManifest, ...] = (
    _manifest(
        "research_scope_planning",
        "mentor_planning",
        ["scope_research", "build_research_roadmap"],
        ["context_bundle_read@v1", "research_scope_validator@v1"],
        "schema://ResearchScopeCandidate",
    ),
    _manifest(
        "research_feasibility_assessment",
        "mentor_planning",
        ["assess_feasibility"],
        ["feasibility_checker@v1"],
        "schema://FeasibilityReport",
    ),
    _manifest(
        "bounded_corpus_review",
        "evidence_review",
        ["synthesize_evidence"],
        ["context_bundle_read@v1", "knowledge_base_search@v1"],
        "schema://BoundedEvidenceSynthesis",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "source_screening",
        "evidence_review",
        ["screen_evidence"],
        ["source_verification_checker@v1"],
        "schema://ScreeningLedger",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "citation_grounding",
        "evidence_review",
        ["screen_evidence", "synthesize_evidence"],
        ["evidence_ref_validate@v1"],
        "schema://EvidenceSufficiencyReport",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "research_question_formulation",
        "research_design",
        ["draft_study_protocol", "define_estimand"],
        ["research_question_validator@v1"],
        "schema://ResearchQuestionCandidate",
    ),
    _manifest(
        "protocol_draft_validation",
        "research_design",
        ["draft_study_protocol", "draft_preregistration"],
        ["protocol_schema_validator@v1"],
        "schema://StudyProtocolValidationReport",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "data_readiness_audit",
        "data_analysis",
        ["audit_data"],
        ["dataset_schema_profile@v1", "data_quality_audit@v1"],
        "schema://AnalysisReadinessReport",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "result_card_generation",
        "data_analysis",
        ["bound_result_interpretation"],
        ["result_validation_checker@v1", "statistical_result_card_builder@v1"],
        "schema://StatisticalResultCardCandidate",
        risk=RiskLevel.HIGH,
    ),
    _manifest(
        "atomic_claim_graph_construction",
        "paper_writing",
        ["draft_manuscript", "map_claims_to_evidence"],
        ["atomic_claim_validator@v1", "claim_evidence_mapper@v1"],
        "schema://AtomicClaimGraph",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "bilingual_manuscript_rendering",
        "paper_writing",
        ["draft_manuscript"],
        ["manuscript_renderer_zh@v1", "manuscript_renderer_en@v1", "bilingual_consistency_checker@v1"],
        "schema://ManuscriptDraft",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "citation_review",
        "independent_review",
        ["review_citations"],
        ["citation_audit@v1", "evidence_reference_audit@v1"],
        "schema://ReviewFinding",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "methodology_review",
        "independent_review",
        ["review_method"],
        ["method_protocol_alignment_checker@v1", "statistical_claim_audit@v1"],
        "schema://ReviewFinding",
        risk=RiskLevel.MEDIUM,
    ),
    _manifest(
        "reproducibility_review",
        "independent_review",
        ["review_reproducibility"],
        ["reproducibility_artifact_audit@v1", "bilingual_draft_audit@v1"],
        "schema://ReviewFinding",
        risk=RiskLevel.MEDIUM,
    ),
)


BUILTIN_SKILL_REFS: dict[str, tuple[str, ...]] = {
    agent_id: tuple(
        f"{manifest.skill_id}@{manifest.skill_version}"
        for manifest in BUILTIN_SKILLS
        if agent_id in manifest.agent_ids
    )
    for agent_id in {
        agent for manifest in BUILTIN_SKILLS for agent in manifest.agent_ids
    }
}


BUILTIN_TOOL_REFS: dict[str, tuple[str, ...]] = {
    agent_id: tuple(
        sorted(
            {
                tool_id
                for manifest in BUILTIN_SKILLS
                if agent_id in manifest.agent_ids
                for tool_id in manifest.required_tool_ids
            }
        )
    )
    for agent_id in {
        agent for manifest in BUILTIN_SKILLS for agent in manifest.agent_ids
    }
}


__all__ = ["BUILTIN_SKILLS", "BUILTIN_SKILL_REFS", "BUILTIN_TOOL_REFS"]

