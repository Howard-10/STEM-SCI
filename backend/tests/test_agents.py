"""Contract and permission tests for the six Phase 1 agent boundaries."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stem_sci.agents import (
    AgentInput,
    AgentResult,
    CandidateArtifact,
    DataAnalysisAgent,
    EvidenceReviewAgent,
    IndependentReviewAgent,
    MentorPlanningAgent,
    PaperWritingAgent,
    ResearchDesignAgent,
    ToolRequest,
)
from stem_sci.controller.merger import validate_agent_result
from stem_sci.core.claims import AtomicClaim, ClaimType
from stem_sci.research_protocol import PreregisteredAnalysisPlan

AGENT_TYPES = (
    MentorPlanningAgent,
    EvidenceReviewAgent,
    ResearchDesignAgent,
    DataAnalysisAgent,
    PaperWritingAgent,
    IndependentReviewAgent,
)


@pytest.mark.parametrize("agent_type", AGENT_TYPES)
def test_each_agent_returns_structured_candidate_result(agent_type: type) -> None:
    """Every role can run without an LLM and only proposes allowed artifacts."""
    agent = agent_type()
    agent_input = AgentInput(
        agent_run_id=f"run-{agent.agent_id}",
        task_ref="task-demo",
        context_bundle_ref="context-demo",
        allowed_tool_capabilities=list(agent.allowed_tool_capabilities),
        allowed_output_types=list(agent.allowed_output_types),
        policy_version="policy-v1",
        prompt_template_version="prompt-v1",
    )

    result = agent.run(agent_input)

    assert result.agent_id == agent.agent_id
    assert result.agent_run_id == agent_input.agent_run_id
    assert result.candidate_artifact_refs
    assert all(ref.startswith(f"candidate://{agent.agent_id}/") for ref in result.candidate_artifact_refs)
    assert result.approval_requests == []
    assert agent.capability().read_only_global_state is True
    assert set(agent.capability().forbidden_actions) == {
        "new_current_stage",
        "approved",
        "freeze_dataset",
        "official_result",
        "publish",
    }


def test_agent_result_rejects_governance_fields() -> None:
    """Agent output cannot smuggle Controller operations through extra fields."""
    payload = {
        "agent_run_id": "run-1",
        "agent_id": "mentor_planning",
        "agent_version": "phase1-scaffold",
        "candidate_artifact_refs": [],
        "tool_requests": [],
        "approval_requests": [],
        "risk_flags": [],
        "unresolved_questions": [],
        "recommendations": [],
        "confidence": 0.5,
        "created_at": datetime.now(UTC),
        "new_current_stage": "RELEASED",
    }

    with pytest.raises(ValidationError):
        AgentResult.model_validate(payload)


def test_agent_respects_controller_output_allow_list() -> None:
    """An agent does not emit artifact types that the Controller did not grant."""
    agent = ResearchDesignAgent()
    result = agent.run(
        AgentInput(
            agent_run_id="run-2",
            task_ref="task-design",
            context_bundle_ref="context-1",
            allowed_tool_capabilities=[],
            allowed_output_types=["StudyProtocolCandidate"],
            policy_version="policy-v1",
            prompt_template_version="prompt-v1",
        )
    )

    assert result.candidate_artifact_refs == [
        "candidate://research_design/task-design/StudyProtocolCandidate"
    ]
    assert "OUTPUT_CAPABILITY_NOT_GRANTED" in result.risk_flags


def test_tool_request_is_structured_and_agent_result_rejects_uri_strings() -> None:
    request = ToolRequest(
        request_id="tool-1",
        capability="literature_search",
        input_refs=["artifact://scope/1"],
        required_output_types=["EvidenceSet"],
        reason="Need project-scoped evidence.",
    )

    assert request.capability == "literature_search"
    with pytest.raises(ValidationError):
        AgentResult(
            agent_run_id="run-structured",
            agent_id="mentor_planning",
            agent_version="phase1-scaffold",
            tool_requests=["request://literature_search"],  # type: ignore[list-item]
            created_at=datetime.now(UTC),
        )


def test_candidate_content_must_match_public_candidate_reference() -> None:
    result = AgentResult(
        agent_run_id="run-content",
        agent_id="evidence_review",
        agent_version="v1",
        candidate_artifact_refs=[
            "candidate://evidence_review/task/EvidenceSufficiencyReport"
        ],
        candidate_artifacts=[
            CandidateArtifact(
                candidate_ref="candidate://evidence_review/task/EvidenceSufficiencyReport",
                artifact_type="BoundedEvidenceSynthesis",
                schema_version="v1",
                body={"status": "READY"},
            )
        ],
        created_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="candidate content type"):
        validate_agent_result(result, EvidenceReviewAgent.capability())


def test_agent_result_serialization_keeps_candidate_artifact_body_for_orchestrators() -> None:
    result = AgentResult(
        agent_run_id="run-serialized-candidate",
        agent_id="mentor_planning",
        agent_version="v1",
        candidate_artifact_refs=["candidate://mentor_planning/task/ResearchScopeCandidate"],
        candidate_artifacts=[
            CandidateArtifact(
                candidate_ref="candidate://mentor_planning/task/ResearchScopeCandidate",
                artifact_type="ResearchScopeCandidate",
                schema_version="v1",
                body={"in_scope": ["physics modelling"]},
            )
        ],
        created_at=datetime.now(UTC),
    )

    payload = result.model_dump(mode="json")

    assert payload["candidate_artifacts"][0]["body"]["in_scope"] == ["physics modelling"]


def test_preregistered_plan_requires_approval_before_freeze() -> None:
    """The plan model distinguishes a candidate from an approved frozen plan."""
    common = {
        "plan_id": "plan-1",
        "primary_outcomes": ["transfer_score"],
        "confirmatory_models": ["linear_mixed_model"],
        "missing_data_strategy": "multiple_imputation",
        "outlier_strategy": "predefined_rule",
        "alpha": 0.05,
        "multiple_comparison_strategy": "holm",
        "exploratory_analysis_policy": "label_exploratory",
    }

    assert PreregisteredAnalysisPlan(**common).status == "candidate"
    with pytest.raises(ValidationError):
        PreregisteredAnalysisPlan(**common, status="frozen", frozen_at=datetime.now(UTC))

    frozen = PreregisteredAnalysisPlan(
        **common,
        status="frozen",
        approval_ref="approval-1",
        frozen_at=datetime.now(UTC),
    )
    assert frozen.status == "frozen"


def test_atomic_claim_has_one_claim_type() -> None:
    """Composite RESULT+INTERPRETATION labels are rejected."""
    claim = AtomicClaim(
        claim_id="claim-1",
        text="The intervention changed transfer performance.",
        claim_type=ClaimType.RESULT,
        result_card_ref="result-card-1",
    )
    assert claim.claim_type is ClaimType.RESULT

    with pytest.raises(ValidationError):
        AtomicClaim(
            claim_id="claim-2",
            text="The intervention changed performance and therefore improved learning.",
            claim_type="RESULT+INTERPRETATION",
        )


def test_independent_reviewer_has_no_execution_capability() -> None:
    """The reviewer can report findings but cannot request execution tools."""
    capability = IndependentReviewAgent.capability()
    assert capability.allowed_tool_capabilities == []
    assert capability.read_only_global_state is True
