"""Controller integration tests for the read-only reproducibility reviewer."""

from __future__ import annotations

from pathlib import Path

from stem_sci.agents import DataAnalysisAgent, DataAnalysisPreAnalysisInput, ManuscriptNumericClaim
from stem_sci.controller import (
    DataPipelineBeginRequest,
    PlanningRequest,
    ReproducibilityReviewRequest,
    ResearchController,
)
from stem_sci.core.enums import ProjectStage
from stem_sci.research_data.demo import write_synthetic_demo_seed
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import AnalysisModelSpecification


def _drafted_controller(tmp_path: Path, project_id: str) -> tuple[ResearchController, str, str, float]:
    controller = ResearchController(data_pipeline_root=tmp_path)
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="physics STEM", run_id=f"{project_id}-p")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")
    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="r")
    design = controller.run_next(project_id)
    controller.resume_approval(project_id, design.approval_request, decision="approved", decided_by="r")

    pre_analysis = DataAnalysisAgent().propose_pre_analysis(
        DataAnalysisPreAnalysisInput(
            agent_run_id=f"{project_id}-analysis",
            project_id=project_id,
            task_ref=f"{project_id}:pre-analysis",
            study_protocol_ref=f"protocol://{project_id}/v1",
            preregistered_plan_ref=f"prereg-plan://{project_id}/v1",
            preregistered_plan_status="frozen",
            preregistration_approval_ref=f"approval://{project_id}/prereg-v1",
            data_collection_schema_ref=f"schema://{project_id}/collection-v1",
            variable_dictionary_ref=f"dictionary://{project_id}/v1",
            analysis_mode=AnalysisMode.PYTHON_ONLY,
            model_specification_refs=[f"model-spec://{project_id}/main-v1"],
            required_variables=["group", "transfer_score"],
            missingness_checks=["report missingness"],
            range_and_type_checks=["numeric transfer score"],
            privacy_checks=["reject direct identifiers"],
            proposed_processing_steps=["approved lossless processing"],
            missing_data_strategy_ref=f"prereg-plan://{project_id}/missingness",
            diagnostic_checks=["residual check"],
            robustness_checks=["pre-specified sensitivity check"],
        )
    )
    controller.begin_data_pipeline(
        DataPipelineBeginRequest(
            project_id=project_id,
            preregistered_plan_ref=f"prereg-plan://{project_id}/v1",
            preregistration_approval_ref=f"approval://{project_id}/prereg-v1",
            pre_analysis=pre_analysis,
            model_specification=AnalysisModelSpecification(
                model_spec_id="main-v1",
                project_id=project_id,
                model_family="group_mean_difference",
                outcome_variables=["transfer_score"],
                predictor_variables=["group"],
                formula_or_design="mean(transfer_score) by group",
                rationale="Synthetic CSV MVP demonstration.",
            ),
            code_artifact_ref=f"code-artifact://{project_id}/mvp-v1",
        )
    )
    source = write_synthetic_demo_seed(tmp_path / f"{project_id}.csv")
    controller.register_data_pipeline_raw_csv(project_id, filename="demo.csv", content=source.read_bytes())
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    assert pipeline.statistical_result_card is not None

    writing = controller.run_next(project_id)
    controller.resume_approval(project_id, writing.approval_request, decision="approved", decided_by="r")
    assert controller.get_state(project_id).current_stage is ProjectStage.DRAFTED
    result_key, result_value = next(iter(pipeline.statistical_result_card.values.items()))
    return controller, writing.approval_request.artifact_ref, result_key, result_value


def test_passing_reproducibility_review_waits_for_human_verification(tmp_path: Path) -> None:
    project_id = "review-pass-demo"
    controller, manuscript_ref, result_key, result_value = _drafted_controller(tmp_path, project_id)
    pipeline = controller._workflow_states[project_id].data_pipeline
    assert pipeline is not None and pipeline.statistical_result_card is not None

    review = controller.run_reproducibility_review(
        ReproducibilityReviewRequest(
            project_id=project_id,
            manuscript_ref=manuscript_ref,
            numeric_claims=[
                ManuscriptNumericClaim(
                    claim_ref="claim://review-pass-demo/result-1",
                    result_card_ref=pipeline.statistical_result_card.ref,
                    result_key=result_key,
                    reported_value=result_value,
                )
            ],
        )
    )

    assert review.outcome.report.overall_recommendation == "PASS"
    assert review.approval_request is not None
    assert review.workflow_state.current_stage is ProjectStage.WAITING_HUMAN
    assert any(
        item.artifact_type == "ReproducibilityReviewReport"
        for item in controller.artifact_content_store.list_project(project_id)
    )
    verified = controller.resume_approval(
        project_id, review.approval_request, decision="approved", decided_by="researcher"
    )
    assert verified.current_stage is ProjectStage.VERIFIED


def test_mismatched_manuscript_number_routes_back_to_writing(tmp_path: Path) -> None:
    project_id = "review-mismatch-demo"
    controller, manuscript_ref, result_key, result_value = _drafted_controller(tmp_path, project_id)
    pipeline = controller._workflow_states[project_id].data_pipeline
    assert pipeline is not None and pipeline.statistical_result_card is not None

    review = controller.run_reproducibility_review(
        ReproducibilityReviewRequest(
            project_id=project_id,
            manuscript_ref=manuscript_ref,
            numeric_claims=[
                ManuscriptNumericClaim(
                    claim_ref="claim://review-mismatch-demo/result-1",
                    result_card_ref=pipeline.statistical_result_card.ref,
                    result_key=result_key,
                    reported_value=result_value + 1,
                )
            ],
        )
    )

    assert review.outcome.report.overall_recommendation == "MAJOR_REVISION"
    assert review.workflow_state.current_stage is ProjectStage.REWORK
    assert review.workflow_state.research_state is not None
    assert review.workflow_state.research_state.rework_target_agent == "paper_writing"
    assert controller.run_next(project_id).route_decision.selected_route == "paper_writing"
