"""Independent acceptance test: every specialist returns substantive candidates.

This is intentionally not a workflow test.  LangGraph/Controller orchestration
remains outside the six-agent capability boundary.
"""

from stem_sci.agents import (
    AgentInput,
    DataAnalysisAgent,
    DataAnalysisPreAnalysisInput,
    EvidenceReviewAgent,
    IndependentReviewAgent,
    MentorPlanningAgent,
    MethodReviewInput,
    PaperWritingAgent,
    PlanningBrief,
    ResearchDesignAgent,
    ResearchDesignBrief,
    ReviewCriterion,
)
from stem_sci.context.models import ContextBundle, EvidenceRef, SourceLocation, VerificationStatus
from stem_sci.controller.merger import validate_agent_result
from stem_sci.agents.writing_pipeline import WritingContextBundle
from stem_sci.statistics.mode_policy import AnalysisMode


def _input(agent_id: str, outputs: tuple[str, ...]) -> AgentInput:
    return AgentInput(
        agent_run_id=f"{agent_id}-acceptance-1",
        task_ref="physics-demo:acceptance",
        context_bundle_ref="context://physics-demo/acceptance",
        allowed_tool_capabilities=[],
        allowed_output_types=list(outputs),
        policy_version="policy-v1",
        prompt_template_version="acceptance-v1",
    )


def _context() -> ContextBundle:
    evidence = EvidenceRef(
        evidence_id="evidence-1",
        project_id="physics-demo",
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="Verified source excerpt about physics modelling support.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=55),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    return ContextBundle(
        context_id="context-1",
        project_id="physics-demo",
        task_ref="physics-demo:acceptance",
        query="AI-supported physics modelling",
        evidence_refs=[evidence],
        source_refs=["source-1"],
        verification_summary={"source_verified": 1},
        token_budget=500,
        estimated_tokens=20,
        context_hash="a" * 64,
        generated_at="2026-08-11T00:00:00Z",
    )


def test_all_six_agents_return_substantive_candidate_packages_without_orchestration() -> None:
    planner = MentorPlanningAgent()
    planning = planner.propose(
        PlanningBrief(
            agent_run_id="planning-1",
            project_id="physics-demo",
            task_ref="physics-demo:planning",
            topic="AI scaffolds in physics modelling",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="layered generative-AI scaffolds",
            comparator="static prompts",
            candidate_outcomes=["transfer_score"],
        )
    )
    design = ResearchDesignAgent().propose(
        ResearchDesignBrief(
            agent_run_id="design-1",
            project_id="physics-demo",
            task_ref="physics-demo:design",
            research_contract_ref="candidate://mentor_planning/physics-demo/ResearchContractCandidate",
            population="pre-service physics teachers",
            context="a university programming course",
            intervention="layered generative-AI scaffolds",
            comparator="static prompts",
            primary_outcome="transfer_score",
            design_type="randomized_parallel_repeated_measures",
            measurement_timepoints=["baseline", "post"],
            sampling_approach="eligible course participants",
            ethics_ref="ethics://physics-demo/candidate",
            confirmatory_model="linear_mixed_effects_model",
            missing_data_strategy="pre-specified multiple imputation",
            outlier_strategy="pre-specified influence reporting",
        )
    )
    analysis = DataAnalysisAgent().propose_pre_analysis(
        DataAnalysisPreAnalysisInput(
            agent_run_id="analysis-1",
            project_id="physics-demo",
            task_ref="physics-demo:analysis",
            study_protocol_ref="protocol://physics-demo/approved",
            preregistered_plan_ref="plan://physics-demo/frozen",
            preregistered_plan_status="frozen",
            preregistration_approval_ref="approval://physics-demo/plan",
            data_collection_schema_ref="schema://physics-demo/1",
            variable_dictionary_ref="dictionary://physics-demo/1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            model_specification_refs=["model://physics-demo/main"],
            required_variables=["group", "transfer_score"],
            missingness_checks=["report missingness"],
            range_and_type_checks=["numeric score"],
            privacy_checks=["reject direct identifiers"],
            proposed_processing_steps=["apply approved processing"],
            missing_data_strategy_ref="plan://physics-demo/missingness",
            diagnostic_checks=["diagnose residuals"],
            robustness_checks=["run pre-specified sensitivity check"],
        )
    )
    evidence_agent = EvidenceReviewAgent()
    writing_agent = PaperWritingAgent()
    context = _context()
    evidence = evidence_agent.run_with_context(
        _input(evidence_agent.agent_id, evidence_agent.allowed_output_types), context
    )
    writing = writing_agent.run_with_context(
        _input(writing_agent.agent_id, writing_agent.allowed_output_types),
        # The fallback only needs approved references; it does not synthesize.
        WritingContextBundle(
            project_id="physics-demo",
            approved_research_scope=context.query,
            evidence_refs=context.evidence_refs,
            approved_study_protocol_refs=["protocol://physics-demo/approved"],
            validated_result_cards=["result-card://physics-demo/1"],
            context_hash="a" * 64,
        ),
    )
    reviewer = IndependentReviewAgent()
    review = reviewer.as_agent_result(
        _input(reviewer.agent_id, reviewer.allowed_output_types),
        reviewer.review_method(
            MethodReviewInput(
                project_id="physics-demo",
                protocol_ref="protocol://physics-demo/approved",
                criteria=[
                    ReviewCriterion(
                        criterion_id="estimand-alignment",
                        artifact_ref="protocol://physics-demo/approved",
                        category="method",
                        description="Approved demonstration criterion.",
                        passed=True,
                    )
                ],
            )
        ),
    )

    assert len(planning.agent_result.candidate_artifacts) == 8
    assert len(design.agent_result.candidate_artifacts) == 15
    assert len(analysis.agent_result.candidate_artifacts) == 8
    assert "PaperCardCollection" in {item.artifact_type for item in evidence.candidate_artifacts}
    assert "ManuscriptOutline" in {item.artifact_type for item in writing.candidate_artifacts}
    assert review.candidate_artifacts[-1].artifact_type == "ReviewReport"
    for result, agent in (
        (planning.agent_result, planner),
        (design.agent_result, ResearchDesignAgent()),
        (analysis.agent_result, DataAnalysisAgent()),
        (evidence, evidence_agent),
        (writing, writing_agent),
        (review, reviewer),
    ):
        assert validate_agent_result(result, agent.capability()) is result
