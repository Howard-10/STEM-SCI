"""FastAPI vertical test for the Controller-owned CSV data pipeline."""

from uuid import uuid4

from fastapi.testclient import TestClient

from stem_sci.agents import DataAnalysisAgent, DataAnalysisPreAnalysisInput
from stem_sci.api import app
from stem_sci.controller import DataPipelineBeginRequest
from stem_sci.research_data.demo import SYNTHETIC_DEMO_COLUMNS, SYNTHETIC_DEMO_ROWS
from stem_sci.statistics.models import AnalysisModelSpecification
from stem_sci.statistics.mode_policy import AnalysisMode


def test_data_pipeline_api_runs_to_verified_python_only_result() -> None:
    client = TestClient(app)
    project_id = f"api-data-{uuid4().hex[:12]}"
    evidence_text = (
        "STEM_SCI_DEMO_SEED: true\n"
        "Synthetic physics STEM evidence for the approved data-pipeline integration test."
    )
    imported = client.post(
        "/api/v1/sources/import",
        data={"project_id": project_id},
        files={"file": ("demo-evidence.txt", evidence_text.encode("utf-8"), "text/plain")},
    )
    assert imported.status_code == 200
    created = client.post(
        "/api/v1/workflow/projects",
        json={"project_id": project_id, "research_intent": "synthetic physics STEM", "run_id": f"{project_id}-p"},
    )
    assert created.status_code == 200
    for _ in range(3):
        approved = client.post(
            f"/api/v1/workflow/projects/{project_id}/approve",
            json={"decision": "approved", "decided_by": "researcher"},
        )
        assert approved.status_code == 200
        if approved.json()["current_stage"] == "STUDY_PROTOCOL_APPROVED":
            break
        next_run = client.post(f"/api/v1/workflow/projects/{project_id}/next")
        assert next_run.status_code == 200

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
    request = DataPipelineBeginRequest(
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
            rationale="Synthetic API demonstration.",
        ),
        code_artifact_ref=f"code-artifact://{project_id}/mvp-v1",
    )
    started = client.post(
        f"/api/v1/workflow/projects/{project_id}/data-pipeline/start",
        json=request.model_dump(mode="json"),
    )
    assert started.status_code == 200
    csv_text = "\n".join(
        [",".join(SYNTHETIC_DEMO_COLUMNS), *[",".join(map(str, row)) for row in SYNTHETIC_DEMO_ROWS]]
    )
    registered = client.post(
        f"/api/v1/workflow/projects/{project_id}/data-pipeline/raw",
        files={"file": ("demo.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert registered.status_code == 200
    assert registered.json()["stage"] == "WAITING_PROCESSING_APPROVAL"
    for expected_stage in (
        "WAITING_FREEZE_APPROVAL",
        "WAITING_EXECUTION_APPROVAL",
        "ANALYZED",
    ):
        decided = client.post(
            f"/api/v1/workflow/projects/{project_id}/data-pipeline/decide",
            json={"decision": "approved", "decided_by": "researcher"},
        )
        assert decided.status_code == 200
        assert decided.json()["stage"] == expected_stage
    assert decided.json()["statistical_result_card"]["execution_status"] == "execution_verified"

    writing = client.post(f"/api/v1/workflow/projects/{project_id}/next")
    assert writing.status_code == 200
    assert writing.json()["route_decision"]["selected_route"] == "paper_writing"
    drafted = client.post(
        f"/api/v1/workflow/projects/{project_id}/approve",
        json={"decision": "approved", "decided_by": "researcher"},
    )
    assert drafted.status_code == 200
    assert drafted.json()["current_stage"] == "DRAFTED"

    result_card = decided.json()["statistical_result_card"]
    result_key, result_value = next(iter(result_card["values"].items()))
    review = client.post(
        f"/api/v1/workflow/projects/{project_id}/reviews/reproducibility",
        json={
            "project_id": project_id,
            "manuscript_ref": writing.json()["approval_request"]["artifact_ref"],
            "numeric_claims": [
                {
                    "claim_ref": f"claim://{project_id}/result-1",
                        "result_card_ref": f"result-card://{result_card['result_id']}",
                    "result_key": result_key,
                    "reported_value": result_value,
                }
            ],
        },
    )
    assert review.status_code == 200
    assert review.json()["outcome"]["report"]["overall_recommendation"] == "PASS"
    assert review.json()["workflow_state"]["current_stage"] == "WAITING_HUMAN"
    verified = client.post(
        f"/api/v1/workflow/projects/{project_id}/approve",
        json={"decision": "approved", "decided_by": "researcher"},
    )
    assert verified.status_code == 200
    assert verified.json()["current_stage"] == "VERIFIED"
