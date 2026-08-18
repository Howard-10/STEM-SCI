"""Behaviour tests for the structured planning and design candidate packages."""

from stem_sci.agents import (
    AgentInput,
    MentorPlanningAgent,
    MentorPlanningPipeline,
    PlanningBrief,
    ResearchDesignAgent,
    ResearchDesignBrief,
    ResearchDesignPipeline,
)
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator


def test_mentor_planning_compiles_a_bounded_candidate_package() -> None:
    outcome = MentorPlanningAgent().propose(
        PlanningBrief(
            agent_run_id="planning-1",
            project_id="physics-demo",
            task_ref="scope-1",
            topic="AI scaffolds in physics modelling",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            candidate_outcomes=["unassisted transfer performance", "prompt dependency"],
            constraints=["one semester", "no direct identifiers"],
            exclusions=["general claims about all STEM disciplines"],
            evidence_refs=["evidence://physics-demo/1"],
        )
    )

    assert outcome.question_tree.primary_question.startswith("For pre-service physics teachers")
    assert outcome.feasibility_report.status == "CANDIDATE_FEASIBLE"
    assert outcome.literature_requirement.minimum_verification_status == "source_verified"
    assert outcome.risk_profile.requires_human_confirmation is True
    assert len(outcome.agent_result.candidate_artifacts) == 8
    assert outcome.agent_result.approval_requests == []
    assert "SCOPE_REQUIRES_CONTROLLER_GATE" in outcome.agent_result.risk_flags


def test_research_design_preserves_pre_data_approval_boundary() -> None:
    outcome = ResearchDesignAgent().propose(
        ResearchDesignBrief(
            agent_run_id="design-1",
            project_id="physics-demo",
            task_ref="protocol-1",
            research_contract_ref="artifact://physics-demo/research-contract/1",
            evidence_refs=["evidence://physics-demo/1"],
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            primary_outcome="unassisted_transfer_score",
            secondary_outcomes=["prompt_dependency"],
            design_type="randomized_parallel_repeated_measures",
            measurement_timepoints=["baseline", "post-task-c"],
            sampling_approach="recruit eligible course participants",
            ethics_ref="ethics://physics-demo/approved-pending-controller-check",
            confirmatory_model="linear_mixed_effects_model",
            covariates=["baseline_score"],
            exclusion_rules=["pre-registered technical failure rule"],
            missing_data_strategy="pre-specified multiple imputation",
            outlier_strategy="pre-specified influence reporting",
        )
    )

    assert outcome.study_protocol_candidate.approval_required is True
    assert outcome.preregistered_analysis_plan_draft.status == "candidate"
    assert outcome.preregistered_analysis_plan_draft.requires_human_approval_before_data_collection
    assert outcome.measurement_plan_candidate.data_dictionary_fields[0] == "participant_id_pseudonym"
    assert "direct_identifiers_allowed" in str(outcome.agent_result.candidate_artifacts)
    assert len(outcome.agent_result.candidate_artifacts) == 15
    assert outcome.agent_result.approval_requests == []


def test_planning_and_design_can_attach_typed_model_rationale_without_approval_authority() -> None:
    planning_pipeline = MentorPlanningPipeline(
        generator=StructuredGenerator(
            FakeLLMProvider(
                [
                    {
                        "primary_question_rationale": "Candidate rationale based only on the supplied brief.",
                        "feasibility_assumptions": ["Recruitment remains to be confirmed."],
                        "feasibility_risks": ["Measurement validity requires review."],
                        "evidence_needs": ["Comparable verified studies."],
                        "unresolved_questions": ["Confirm ethics requirements."],
                    }
                ]
            )
        ),
        model="gpt-test",
    )
    planning = MentorPlanningAgent(pipeline=planning_pipeline).propose_with_model(
        PlanningBrief(
            agent_run_id="planning-model-1",
            project_id="physics-demo",
            task_ref="scope-model-1",
            topic="AI scaffolds in physics modelling",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            candidate_outcomes=["unassisted transfer performance"],
        )
    )
    design_pipeline = ResearchDesignPipeline(
        generator=StructuredGenerator(
            FakeLLMProvider(
                [
                    {
                        "estimand_rationale": "Candidate contrast rationale.",
                        "allocation_risk_notes": ["Avoid condition crossover."],
                        "measurement_validity_questions": ["Review transfer-task equivalence."],
                        "analysis_boundary_notes": ["Do not alter frozen primary outcomes."],
                        "preregistration_risks": ["Amendments require human approval."],
                    }
                ]
            )
        ),
        model="gpt-test",
    )
    design = ResearchDesignAgent(pipeline=design_pipeline).propose_with_model(
        ResearchDesignBrief(
            agent_run_id="design-model-1",
            project_id="physics-demo",
            task_ref="protocol-model-1",
            research_contract_ref="artifact://physics-demo/research-contract/1",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            primary_outcome="unassisted_transfer_score",
            design_type="randomized_parallel_repeated_measures",
            measurement_timepoints=["baseline", "post-task-c"],
            sampling_approach="recruit eligible course participants",
            ethics_ref="ethics://physics-demo/candidate",
            confirmatory_model="linear_mixed_effects_model",
            missing_data_strategy="pre-specified multiple imputation",
            outlier_strategy="pre-specified influence reporting",
        )
    )

    assert planning.model_assisted_rationale is not None
    assert design.model_assisted_rationale is not None
    assert planning.agent_result.candidate_artifacts[-1].artifact_type == "PlanningRationaleCandidate"
    assert design.agent_result.candidate_artifacts[-1].artifact_type == "DesignRationaleCandidate"
    assert planning.agent_result.approval_requests == []
    assert design.agent_result.approval_requests == []


def test_planner_and_design_authorized_entrypoints_omit_ungranted_outputs() -> None:
    planner = MentorPlanningAgent()
    planning_brief = PlanningBrief(
        agent_run_id="planning-authorized-1",
        project_id="physics-demo",
        task_ref="scope-authorized-1",
        topic="AI scaffolds in physics modelling",
        population="pre-service physics teachers",
        context="a university programming course",
        intervention="generative-AI layered scaffolds",
        comparator="static prompts",
        candidate_outcomes=["unassisted transfer performance"],
    )
    planning = planner.propose_for(
        AgentInput(
            agent_run_id=planning_brief.agent_run_id,
            task_ref=planning_brief.task_ref,
            context_bundle_ref="context://physics-demo/planning",
            allowed_tool_capabilities=[],
            allowed_output_types=["ResearchQuestionTree"],
            policy_version="policy-v1",
            prompt_template_version="planning-v1",
        ),
        planning_brief,
    )
    design_agent = ResearchDesignAgent()
    design_brief = ResearchDesignBrief(
        agent_run_id="design-authorized-1",
        project_id="physics-demo",
        task_ref="design-authorized-1",
        research_contract_ref="artifact://physics-demo/research-contract/1",
        population="pre-service physics teachers",
        context="a university programming course",
        intervention="generative-AI layered scaffolds",
        comparator="static prompts",
        primary_outcome="unassisted_transfer_score",
        design_type="randomized_parallel_repeated_measures",
        measurement_timepoints=["baseline", "post-task-c"],
        sampling_approach="recruit eligible course participants",
        ethics_ref="ethics://physics-demo/candidate",
        confirmatory_model="linear_mixed_effects_model",
        missing_data_strategy="pre-specified multiple imputation",
        outlier_strategy="pre-specified influence reporting",
    )
    design = design_agent.propose_for(
        AgentInput(
            agent_run_id=design_brief.agent_run_id,
            task_ref=design_brief.task_ref,
            context_bundle_ref="context://physics-demo/design",
            allowed_tool_capabilities=[],
            allowed_output_types=["StudyProtocolCandidate"],
            policy_version="policy-v1",
            prompt_template_version="design-v1",
        ),
        design_brief,
    )

    assert [item.artifact_type for item in planning.agent_result.candidate_artifacts] == [
        "ResearchQuestionTree"
    ]
    assert [item.artifact_type for item in design.agent_result.candidate_artifacts] == [
        "StudyProtocolCandidate"
    ]
    assert "OUTPUT_CAPABILITY_NOT_GRANTED" in planning.agent_result.risk_flags
    assert "OUTPUT_CAPABILITY_NOT_GRANTED" in design.agent_result.risk_flags


def test_model_generation_failure_falls_back_to_deterministic_planning_and_design() -> None:
    planning_pipeline = MentorPlanningPipeline(
        generator=StructuredGenerator(FakeLLMProvider([]), max_retries=0), model="gpt-test"
    )
    planning = MentorPlanningAgent(pipeline=planning_pipeline).propose_with_model(
        PlanningBrief(
            agent_run_id="planning-failure-1",
            project_id="physics-demo",
            task_ref="scope-failure-1",
            topic="AI scaffolds in physics modelling",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            candidate_outcomes=["unassisted transfer performance"],
        )
    )
    design_pipeline = ResearchDesignPipeline(
        generator=StructuredGenerator(FakeLLMProvider([]), max_retries=0), model="gpt-test"
    )
    design = ResearchDesignAgent(pipeline=design_pipeline).propose_with_model(
        ResearchDesignBrief(
            agent_run_id="design-failure-1",
            project_id="physics-demo",
            task_ref="design-failure-1",
            research_contract_ref="artifact://physics-demo/research-contract/1",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="generative-AI layered scaffolds",
            comparator="static prompts",
            primary_outcome="unassisted_transfer_score",
            design_type="randomized_parallel_repeated_measures",
            measurement_timepoints=["baseline", "post-task-c"],
            sampling_approach="recruit eligible course participants",
            ethics_ref="ethics://physics-demo/candidate",
            confirmatory_model="linear_mixed_effects_model",
            missing_data_strategy="pre-specified multiple imputation",
            outlier_strategy="pre-specified influence reporting",
        )
    )

    assert "MODEL_GENERATION_FAILED" in planning.agent_result.risk_flags
    assert "MODEL_GENERATION_FAILED" in design.agent_result.risk_flags
    assert planning.model_assisted_rationale is None
    assert design.model_assisted_rationale is None
