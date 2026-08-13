"""Mentor/planning Agent that produces structured, approval-bound candidates."""

from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from .base import BaseAgent
from .contracts import AgentContract, AgentInput, AgentResult, CandidateArtifact
from .planning_contracts import (
    FeasibilityReport,
    InitialRiskProfile,
    LiteratureRequirement,
    MentorPlanningOutcome,
    PlanningBrief,
    ProjectRoadmap,
    ResearchQuestionTree,
)
from .research_generation import MentorPlanningPipeline, PlanningRationaleCandidate
from .runtime import StructuredGenerationError


class MentorPlanningAgent(BaseAgent):
    agent_id = "mentor_planning"
    supported_task_types = ("scope_research", "build_research_roadmap", "assess_feasibility")
    allowed_tool_capabilities = ("literature_search_request",)
    allowed_output_types = (
        "ResearchContractCandidate",
        "FeasibilityReport",
        "ResearchQuestionTree",
        "ResearchScopeCandidate",
        "ProjectRoadmap",
        "LiteratureRequirementList",
        "InitialRiskProfile",
        "UnresolvedQuestionList",
        "PlanningRationaleCandidate",
    )

    def __init__(self, pipeline: MentorPlanningPipeline | None = None) -> None:
        self.pipeline = pipeline

    def propose(self, brief: PlanningBrief) -> MentorPlanningOutcome:
        """Compile a supplied brief without making empirical or approval claims."""

        prefix = f"candidate://{self.agent_id}/{brief.task_ref}"
        primary_question = (
            f"For {brief.population} in {brief.context}, how does {brief.intervention} "
            f"compare with {brief.comparator} on {brief.candidate_outcomes[0]}?"
        )
        feasibility = FeasibilityReport(
            report_id=f"{brief.project_id}:feasibility:candidate",
            project_id=brief.project_id,
            status="CANDIDATE_FEASIBLE" if brief.constraints else "NEEDS_SCOPING",
            assumptions=[
                "The stated population can be recruited under an approved protocol.",
                "The candidate outcome can be measured with a documented rubric or instrument.",
            ],
            constraints=brief.constraints,
            risks=[
                "Feasibility is a planning judgement, not evidence that recruitment or ethics approval exists."
            ],
            required_confirmations=[
                "Confirm ethics and data-governance requirements.",
                "Confirm access to the target population and measurement resources.",
            ],
        )
        questions = ResearchQuestionTree(
            tree_id=f"{brief.project_id}:questions:candidate",
            project_id=brief.project_id,
            primary_question=primary_question,
            secondary_questions=[
                f"How does the intervention relate to {outcome}?"
                for outcome in brief.candidate_outcomes[1:]
            ],
            out_of_scope_questions=brief.exclusions,
        )
        roadmap = ProjectRoadmap(
            roadmap_id=f"{brief.project_id}:roadmap:candidate",
            project_id=brief.project_id,
            milestones=[
                "Scope and research question candidate reviewed.",
                "Evidence matrix screened and source-verified.",
                "Study protocol and preregistered analysis plan approved before data collection.",
                "Data audit, processing approval, and deterministic dataset freeze completed.",
                "Deterministic execution, result validation, independent review, and human release review completed.",
            ],
            human_decision_points=[
                "Approve scope and study protocol.",
                "Approve preregistered analysis plan before data collection.",
                "Approve data processing before FrozenDataset creation.",
                "Approve interpretation and release.",
            ],
        )
        literature = LiteratureRequirement(
            requirement_id=f"{brief.project_id}:literature-requirements:candidate",
            project_id=brief.project_id,
            required_evidence_categories=[
                "domain and pedagogical theory",
                "intervention or scaffold design evidence",
                "outcome measurement validity evidence",
                "comparable empirical study evidence",
            ],
            screening_questions=[
                "Does the source address the target population or an explicitly comparable population?",
                "Does it support a bounded claim rather than a broad conclusion?",
                "Is its verification status sufficient for formal use?",
            ],
        )
        risks = InitialRiskProfile(
            profile_id=f"{brief.project_id}:initial-risks:candidate",
            project_id=brief.project_id,
            risks=[
                "Unverified sources cannot support formal literature conclusions.",
                "A change to confirmatory decisions after results are viewed requires an amendment and human approval.",
                "Any personal data must be de-identified before processing.",
            ],
            mitigations=[
                "Use source_verified or human_verified evidence for formal claims.",
                "Freeze the preregistered analysis plan before data collection.",
                "Use a deterministic data audit before creating a FrozenDataset.",
            ],
        )
        artifacts = [
            self._artifact(prefix, "ResearchContractCandidate", {
                "project_id": brief.project_id,
                "topic": brief.topic,
                "population": brief.population,
                "context": brief.context,
                "intervention": brief.intervention,
                "comparator": brief.comparator,
                "outcomes": brief.candidate_outcomes,
                "constraints": brief.constraints,
                "exclusions": brief.exclusions,
            }),
            self._artifact(prefix, "FeasibilityReport", feasibility),
            self._artifact(prefix, "ResearchQuestionTree", questions),
            self._artifact(prefix, "ResearchScopeCandidate", {
                "in_scope": [brief.topic, brief.population, brief.context],
                "out_of_scope": brief.exclusions,
            }),
            self._artifact(prefix, "ProjectRoadmap", roadmap),
            self._artifact(prefix, "LiteratureRequirementList", literature),
            self._artifact(prefix, "InitialRiskProfile", risks),
            self._artifact(prefix, "UnresolvedQuestionList", {
                "items": feasibility.required_confirmations,
            }),
        ]
        result = AgentResult(
            agent_run_id=brief.agent_run_id,
            agent_id=self.agent_id,
            agent_version="phase1-structured-planning",
            candidate_artifact_refs=[item.candidate_ref for item in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=brief.evidence_refs,
            risk_flags=["SCOPE_REQUIRES_CONTROLLER_GATE"],
            unresolved_questions=feasibility.required_confirmations,
            recommendations=[
                "Controller must persist candidates and route scope approval; this Agent cannot approve scope."
            ],
            confidence=0.6 if brief.evidence_refs else 0.4,
            created_at=datetime.now(UTC),
        )
        return MentorPlanningOutcome(
            agent_result=result,
            feasibility_report=feasibility,
            question_tree=questions,
            roadmap=roadmap,
            literature_requirement=literature,
            risk_profile=risks,
        )

    def propose_with_model(self, brief: PlanningBrief) -> MentorPlanningOutcome:
        """Add audited model rationale without changing deterministic candidates."""

        if self.pipeline is None:
            raise ValueError("mentor planning pipeline is not configured")
        base = self.propose(brief)
        try:
            generated = self.pipeline.run(brief)
        except StructuredGenerationError:
            return self._model_generation_fallback(base)
        parsed = generated.parsed_output
        assert isinstance(parsed, PlanningRationaleCandidate)
        rationale = parsed.model_dump(mode="json")
        artifact = self._artifact(
            f"candidate://{self.agent_id}/{brief.task_ref}",
            "PlanningRationaleCandidate",
            rationale,
        )
        result = base.agent_result.model_copy(
            update={
                "agent_version": "phase1-model-assisted-planning-v1",
                "candidate_artifact_refs": [*base.agent_result.candidate_artifact_refs, artifact.candidate_ref],
                "candidate_artifacts": [*base.agent_result.candidate_artifacts, artifact],
                "llm_metadata_refs": [f"llm-metadata://{brief.project_id}/{generated.request_id}"],
                "risk_flags": [*base.agent_result.risk_flags, "MODEL_RATIONALE_REQUIRES_GATE"],
            }
        )
        return base.model_copy(update={"agent_result": result, "model_assisted_rationale": rationale})

    def propose_for(
        self, agent_input: AgentInput, brief: PlanningBrief, *, model_assisted: bool = False
    ) -> MentorPlanningOutcome:
        """Produce a planner package and expose only controller-granted outputs."""

        if brief.agent_run_id != agent_input.agent_run_id or brief.task_ref != agent_input.task_ref:
            raise ValueError("PlanningBrief must match AgentInput run and task references")
        if model_assisted and self.pipeline is None:
            outcome = self._model_generation_fallback(self.propose(brief))
        else:
            outcome = self.propose_with_model(brief) if model_assisted else self.propose(brief)
        return outcome.model_copy(
            update={"agent_result": self.restrict_to_authorized_outputs(agent_input, outcome.agent_result)}
        )

    @staticmethod
    def _model_generation_fallback(base: MentorPlanningOutcome) -> MentorPlanningOutcome:
        result = base.agent_result.model_copy(
            update={
                "risk_flags": [*base.agent_result.risk_flags, "MODEL_GENERATION_FAILED"],
                "unresolved_questions": [
                    *base.agent_result.unresolved_questions,
                    "Model-assisted planning rationale is unavailable; review deterministic candidates.",
                ],
            }
        )
        return base.model_copy(update={"agent_result": result})

    @staticmethod
    def _artifact(
        prefix: str, artifact_type: str, body: AgentContract | dict[str, object],
    ) -> CandidateArtifact:
        payload = body if isinstance(body, dict) else body.model_dump(mode="json")
        return CandidateArtifact(
            candidate_ref=f"{prefix}/{artifact_type}",
            artifact_type=artifact_type,
            schema_version="v1",
            body=cast(dict[str, JsonValue], payload),
        )
