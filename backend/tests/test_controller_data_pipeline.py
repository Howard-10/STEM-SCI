"""Controller-owned CSV/PYTHON_ONLY pipeline acceptance tests."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from stem_sci.agents import DataAnalysisAgent, DataAnalysisPreAnalysisInput
from stem_sci.controller import DataPipelineBeginRequest, DataPipelineStage, PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage
from stem_sci.research_data.demo import write_synthetic_demo_seed
from stem_sci.statistics.models import AnalysisModelSpecification
from stem_sci.statistics.mode_policy import AnalysisMode


def _ready_controller(tmp_path: Path, project_id: str) -> ResearchController:
    controller = ResearchController(data_pipeline_root=tmp_path)
    planning = controller.start_planning(
        PlanningRequest(project_id=project_id, research_intent="physics STEM", run_id=f"{project_id}-p")
    )
    controller.resume_approval(project_id, planning.approval_request, decision="approved", decided_by="r")
    evidence = controller.run_next(project_id)
    controller.resume_approval(project_id, evidence.approval_request, decision="approved", decided_by="r")
    design = controller.run_next(project_id)
    controller.resume_approval(project_id, design.approval_request, decision="approved", decided_by="r")
    assert controller.get_state(project_id).current_stage is ProjectStage.STUDY_PROTOCOL_APPROVED
    return controller


def _start_pipeline(
    controller: ResearchController, project_id: str, *, unknown_predictor: bool = False
):
    pre_analysis = DataAnalysisAgent().propose_pre_analysis(
        DataAnalysisPreAnalysisInput(
            agent_run_id=f"{project_id}-analysis",
            project_id=project_id,
            task_ref=f"{project_id}:pre-analysis",
            study_protocol_ref=f"protocol://{project_id}/v1",
            preregistered_plan_ref=f"prereg-plan://{project_id}/v1",
            preregistered_plan_status="approved",
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
    return controller.begin_data_pipeline(
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
                predictor_variables=["missing_predictor"] if unknown_predictor else ["group"],
                formula_or_design="mean(transfer_score) by group",
                rationale="Synthetic CSV MVP demonstration.",
            ),
            code_artifact_ref=f"code-artifact://{project_id}/mvp-v1",
        )
    )


def test_controller_runs_approved_csv_pipeline_to_verified_result(tmp_path: Path) -> None:
    project_id = "controller-data-pass"
    controller = _ready_controller(tmp_path, project_id)
    pipeline = _start_pipeline(controller, project_id)
    assert pipeline.stage is DataPipelineStage.WAITING_RAW_DATA

    source = write_synthetic_demo_seed(tmp_path / "demo.csv")
    pipeline = controller.register_data_pipeline_raw_csv(
        project_id, filename="demo.csv", content=source.read_bytes()
    )
    assert pipeline.stage is DataPipelineStage.WAITING_PROCESSING_APPROVAL
    assert pipeline.data_audit_report is not None and pipeline.data_audit_report.passed

    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    assert pipeline.stage is DataPipelineStage.WAITING_FREEZE_APPROVAL
    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    assert pipeline.stage is DataPipelineStage.WAITING_EXECUTION_APPROVAL
    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")

    assert pipeline.stage is DataPipelineStage.ANALYZED
    assert pipeline.validation_report is not None and pipeline.validation_report.passed
    assert pipeline.statistical_result_card is not None
    assert pipeline.statistical_result_card.execution_status == "execution_verified"
    assert controller.get_state(project_id).current_stage is ProjectStage.ANALYZED


def test_verified_result_card_is_available_to_the_writing_context(tmp_path: Path) -> None:
    """Writing RESULT claims receive only the Controller-built result-card reference."""

    project_id = "controller-data-writing-context"
    controller = _ready_controller(tmp_path, project_id)
    _start_pipeline(controller, project_id)
    source = write_synthetic_demo_seed(tmp_path / "demo.csv")
    controller.register_data_pipeline_raw_csv(project_id, filename="demo.csv", content=source.read_bytes())
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")

    assert pipeline.statistical_result_card is not None
    workflow_state = controller._workflow_states[project_id]
    context = controller._build_writing_context(project_id, "draft_manuscript", workflow_state)

    assert pipeline.statistical_result_card.ref in context.validated_result_cards


def test_controller_blocks_tampered_frozen_dataset_before_execution(tmp_path: Path) -> None:
    project_id = "controller-data-tamper"
    controller = _ready_controller(tmp_path, project_id)
    _start_pipeline(controller, project_id)
    source = write_synthetic_demo_seed(tmp_path / "demo.csv")
    controller.register_data_pipeline_raw_csv(project_id, filename="demo.csv", content=source.read_bytes())
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")
    assert pipeline.frozen_dataset is not None
    frozen_path = Path(pipeline.frozen_dataset.content_uri)
    os.chmod(frozen_path, stat.S_IWRITE | stat.S_IREAD)
    frozen_path.write_text("group,transfer_score\nai_scaffold,999\n", encoding="utf-8")

    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")

    assert pipeline.stage is DataPipelineStage.BLOCKED
    assert pipeline.statistical_result_card is None
    assert controller.get_state(project_id).current_stage is ProjectStage.BLOCKED


def test_controller_routes_invalid_raw_csv_to_rework_without_processing(tmp_path: Path) -> None:
    project_id = "controller-data-audit"
    controller = _ready_controller(tmp_path, project_id)
    _start_pipeline(controller, project_id)

    pipeline = controller.register_data_pipeline_raw_csv(
        project_id, filename="invalid.csv", content=b"group\nai_scaffold\n"
    )

    assert pipeline.stage is DataPipelineStage.REWORK
    assert pipeline.processed_dataset is None
    assert pipeline.data_audit_report is not None
    assert pipeline.data_audit_report.missing_required_variables == ["transfer_score"]
    assert controller.get_state(project_id).current_stage is ProjectStage.REWORK


def test_controller_schema_gate_routes_incompatible_frozen_csv_to_rework(tmp_path: Path) -> None:
    project_id = "controller-schema-rework"
    controller = _ready_controller(tmp_path, project_id)
    _start_pipeline(controller, project_id, unknown_predictor=True)
    source = write_synthetic_demo_seed(tmp_path / "demo.csv")
    controller.register_data_pipeline_raw_csv(project_id, filename="demo.csv", content=source.read_bytes())
    controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")

    pipeline = controller.decide_data_pipeline(project_id, decision="approved", decided_by="researcher")

    assert pipeline.stage is DataPipelineStage.REWORK
    assert pipeline.gate_results[-1].gate_id == "SchemaCompatibilityGate"
    assert pipeline.gate_results[-1].missing_fields == ["missing_predictor"]
    assert controller.get_state(project_id).current_stage is ProjectStage.REWORK
