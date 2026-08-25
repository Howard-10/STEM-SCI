"""Research-design Agent that compiles bounded protocol candidates."""

from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from .base import BaseAgent
from .contracts import AgentContract, AgentInput, AgentResult, CandidateArtifact
from .design_contracts import (
    AnalysisPlanDraft,
    MeasurementPlanCandidate,
    ResearchDesignBrief,
    ResearchDesignOutcome,
    StudyProtocolCandidate,
)
from .research_generation import DesignRationaleCandidate, ResearchDesignPipeline
from .runtime import StructuredGenerationError


class ResearchDesignAgent(BaseAgent):
    agent_id = "research_design"
    supported_task_types = ("draft_study_protocol", "define_estimand", "draft_preregistration")
    allowed_tool_capabilities = ()
    allowed_output_types = (
        "ResearchQuestionCandidate",
        "HypothesisCandidate",
        "Estimand",
        "CausalDAG",
        "StudyProtocolCandidate",
        "SamplingPlan",
        "InterventionProtocol",
        "ProgrammingTaskSpecification",
        "HintPolicy",
        "CodeRubric",
        "UnitTestSpecification",
        "MeasurementPlan",
        "DataCollectionSchema",
        "PreregisteredAnalysisPlanDraft",
        "QualityGatePlan",
        "DesignRationaleCandidate",
    )

    def __init__(self, pipeline: ResearchDesignPipeline | None = None) -> None:
        self.pipeline = pipeline

    def propose(self, brief: ResearchDesignBrief) -> ResearchDesignOutcome:
        """Produce pre-data candidates while preserving preregistration semantics."""

        prefix = f"candidate://{self.agent_id}/{brief.task_ref}"
        allocation = (
            "Randomly allocate participants to one stable intervention condition; "
            "do not cross intervention conditions."
            if brief.design_type == "randomized_parallel_repeated_measures"
            else "Candidate crossover design only; carryover and sequence risks require separate review."
        )
        protocol = StudyProtocolCandidate(
            protocol_id=f"{brief.project_id}:study-protocol:candidate",
            project_id=brief.project_id,
            research_contract_ref=brief.research_contract_ref,
            design_type=brief.design_type,
            allocation_description=allocation,
            primary_outcome=brief.primary_outcome,
            measurement_timepoints=brief.measurement_timepoints,
            ethics_ref=brief.ethics_ref,
        )
        plan = AnalysisPlanDraft(
            plan_id=f"{brief.project_id}:preregistered-analysis-plan:candidate",
            project_id=brief.project_id,
            primary_outcomes=[brief.primary_outcome],
            secondary_outcomes=brief.secondary_outcomes,
            confirmatory_models=[brief.confirmatory_model],
            covariates=brief.covariates,
            exclusion_rules=brief.exclusion_rules,
            missing_data_strategy=brief.missing_data_strategy,
            outlier_strategy=brief.outlier_strategy,
            analysis_mode=brief.analysis_mode,
        )
        measurement = MeasurementPlanCandidate(
            plan_id=f"{brief.project_id}:measurement-plan:candidate",
            project_id=brief.project_id,
            primary_outcome=brief.primary_outcome,
            secondary_outcomes=brief.secondary_outcomes,
            measurement_timepoints=brief.measurement_timepoints,
            data_dictionary_fields=[
                "participant_id_pseudonym",
                "group",
                "timepoint",
                brief.primary_outcome,
                *brief.secondary_outcomes,
            ],
        )
        artifacts = [
            self._artifact(prefix, "ResearchQuestionCandidate", {
                "population": brief.population,
                "context": brief.context,
                "intervention": brief.intervention,
                "comparator": brief.comparator,
                "outcome": brief.primary_outcome,
            }),
            self._artifact(prefix, "HypothesisCandidate", {
                "text": "Candidate hypothesis pending evidence and protocol approval.",
                "outcome": brief.primary_outcome,
            }),
            self._artifact(prefix, "Estimand", {
                "population": brief.population,
                "treatment": brief.intervention,
                "comparator": brief.comparator,
                "outcome": brief.primary_outcome,
                "time": brief.measurement_timepoints[-1],
                "summary_measure": "pre-specified model contrast",
            }),
            self._artifact(prefix, "CausalDAG", {
                "status": "candidate",
                "required_nodes": ["allocation", "intervention", "outcome", *brief.covariates],
                "warning": "A causal DAG candidate is not causal identification proof.",
            }),
            self._artifact(prefix, "StudyProtocolCandidate", protocol),
            self._artifact(prefix, "SamplingPlan", {
                "approach": brief.sampling_approach,
                "population": brief.population,
                "requires_human_feasibility_confirmation": True,
            }),
            self._artifact(prefix, "InterventionProtocol", {
                "intervention": brief.intervention,
                "comparator": brief.comparator,
                "allocation": allocation,
            }),
            self._artifact(prefix, "ProgrammingTaskSpecification", {
                "status": "candidate",
                "required_equivalence_review": True,
            }),
            self._artifact(prefix, "HintPolicy", {
                "status": "candidate",
                "intervention": brief.intervention,
                "comparator": brief.comparator,
            }),
            self._artifact(prefix, "CodeRubric", {"status": "candidate", "outcome": brief.primary_outcome}),
            self._artifact(prefix, "UnitTestSpecification", {
                "status": "candidate",
                "must_not_access_network": True,
            }),
            self._artifact(prefix, "MeasurementPlan", measurement),
            self._artifact(prefix, "DataCollectionSchema", {
                "fields": measurement.data_dictionary_fields,
                "direct_identifiers_allowed": False,
            }),
            self._artifact(prefix, "PreregisteredAnalysisPlanDraft", plan),
            self._artifact(prefix, "QualityGatePlan", {
                "required_gates": ["StudyProtocolGate", "AnalysisPlanGate", "DataAuditGate"],
                "requires_human_approval_before_data_collection": True,
            }),
        ]
        result = AgentResult(
            agent_run_id=brief.agent_run_id,
            agent_id=self.agent_id,
            agent_version="phase1-structured-design",
            candidate_artifact_refs=[item.candidate_ref for item in artifacts],
            candidate_artifacts=artifacts,
            evidence_refs=brief.evidence_refs,
            risk_flags=["PROTOCOL_AND_PREREGISTRATION_REQUIRE_HUMAN_APPROVAL"],
            unresolved_questions=[
                "Confirm measurement validity, task equivalence, and ethics approval before data collection."
            ],
            recommendations=[
                "Controller must gate and human-approve the StudyProtocol and PreregisteredAnalysisPlan."
            ],
            confidence=0.6 if brief.evidence_refs else 0.4,
            created_at=datetime.now(UTC),
        )
        return ResearchDesignOutcome(
            agent_result=result,
            study_protocol_candidate=protocol,
            preregistered_analysis_plan_draft=plan,
            measurement_plan_candidate=measurement,
        )

    def propose_with_model(self, brief: ResearchDesignBrief) -> ResearchDesignOutcome:
        """Attach a typed model rationale without altering protocol decisions."""

        if self.pipeline is None:
            raise ValueError("research design pipeline is not configured")
        base = self.propose(brief)
        try:
            generated = self.pipeline.run(brief)
        except StructuredGenerationError:
            return self._model_generation_fallback(base)
        parsed = generated.parsed_output
        assert isinstance(parsed, DesignRationaleCandidate)
        rationale = parsed.model_dump(mode="json")
        artifact = self._artifact(
            f"candidate://{self.agent_id}/{brief.task_ref}",
            "DesignRationaleCandidate",
            rationale,
        )
        result = base.agent_result.model_copy(
            update={
                "agent_version": "phase1-model-assisted-design-v1",
                "candidate_artifact_refs": [*base.agent_result.candidate_artifact_refs, artifact.candidate_ref],
                "candidate_artifacts": [*base.agent_result.candidate_artifacts, artifact],
                "llm_metadata_refs": [f"llm-metadata://{brief.project_id}/{generated.request_id}"],
                "risk_flags": [*base.agent_result.risk_flags, "MODEL_RATIONALE_REQUIRES_GATE"],
            }
        )
        return base.model_copy(update={"agent_result": result, "model_assisted_rationale": rationale})

    def propose_for(
        self, agent_input: AgentInput, brief: ResearchDesignBrief, *, model_assisted: bool = False
    ) -> ResearchDesignOutcome:
        """Produce a design package and expose only controller-granted outputs."""

        if brief.agent_run_id != agent_input.agent_run_id or brief.task_ref != agent_input.task_ref:
            raise ValueError("ResearchDesignBrief must match AgentInput run and task references")
        if model_assisted and self.pipeline is None:
            outcome = self._model_generation_fallback(self.propose(brief))
        else:
            outcome = self.propose_with_model(brief) if model_assisted else self.propose(brief)
        return outcome.model_copy(
            update={"agent_result": self.restrict_to_authorized_outputs(agent_input, outcome.agent_result)}
        )

    @staticmethod
    def _model_generation_fallback(base: ResearchDesignOutcome) -> ResearchDesignOutcome:
        result = base.agent_result.model_copy(
            update={
                "risk_flags": [*base.agent_result.risk_flags, "MODEL_GENERATION_FAILED"],
                "unresolved_questions": [
                    *base.agent_result.unresolved_questions,
                    "Model-assisted design rationale is unavailable; review deterministic candidates.",
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
