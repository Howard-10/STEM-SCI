"""Controller-owned CSV/PYTHON_ONLY data-analysis pipeline.

The DataAnalysisAgent supplies candidate specifications.  This module is the
separate deterministic path that applies approved operations and owns pipeline
state transitions.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents.analysis_contracts import DataAnalysisPreAnalysisOutcome
from stem_sci.coding.providers import CodeArtifactStore, DeterministicTemplateCodingProvider
from stem_sci.core.enums import DecisionScope, GateDecision, RunStatus
from stem_sci.core.models import GateResult
from stem_sci.controller.analysis_execution import (
    ResearchAnalysisExecutionRequest,
    ResearchAnalysisExecutionService,
)
from stem_sci.operators.executor import OperatorExecutor
from stem_sci.research_data.freeze import DataFreezeService
from stem_sci.research_data.canonical import canonical_csv_bytes, read_csv_rows
from stem_sci.research_data.models import FrozenDatasetRef, ProcessedDatasetRef, RawDatasetRef
from stem_sci.research_data.processing import DataProcessingService
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    ResultValidationReport,
    StatisticalResultCard,
)
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


class DataPipelineStage(StrEnum):
    WAITING_RAW_DATA = "WAITING_RAW_DATA"
    WAITING_PROCESSING_APPROVAL = "WAITING_PROCESSING_APPROVAL"
    REWORK = "REWORK"
    WAITING_FREEZE_APPROVAL = "WAITING_FREEZE_APPROVAL"
    WAITING_EXECUTION_APPROVAL = "WAITING_EXECUTION_APPROVAL"
    ANALYZED = "ANALYZED"
    BLOCKED = "BLOCKED"


class DataAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    raw_dataset_ref: str = Field(min_length=1)
    passed: bool
    missing_required_variables: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    decision_scope: DecisionScope
    blocked_target_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class DataPipelineApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    approval_type: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class DataPipelineState(BaseModel):
    """Reference-only state for Controller data operations; no file payloads."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    stage: DataPipelineStage
    preregistered_plan_ref: str = Field(min_length=1)
    preregistration_approval_ref: str = Field(min_length=1)
    pre_analysis: DataAnalysisPreAnalysisOutcome
    model_specification: AnalysisModelSpecification
    code_artifact_ref: str | None = None
    code_specification_ref: str | None = None
    code_review_ref: str | None = None
    raw_dataset: RawDatasetRef | None = None
    data_audit_report: DataAuditReport | None = None
    processed_dataset: ProcessedDatasetRef | None = None
    frozen_dataset: FrozenDatasetRef | None = None
    executable_plan: ExecutableAnalysisPlan | None = None
    validation_report: ResultValidationReport | None = None
    statistical_result_card: StatisticalResultCard | None = None
    gate_results: list[GateResult] = Field(default_factory=list)
    pending_approval: DataPipelineApproval | None = None
    rework_reason: str | None = None
    blocked_target_ids: list[str] = Field(default_factory=list)


class DataPipelineBeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    preregistered_plan_ref: str = Field(min_length=1)
    preregistration_approval_ref: str = Field(min_length=1)
    pre_analysis: DataAnalysisPreAnalysisOutcome
    model_specification: AnalysisModelSpecification
    # Kept as a compatibility field for callers compiled before the
    # Controller-owned CodingProvider path.  A real artifact is created only
    # after FrozenDataset and ExecutableAnalysisPlan exist.
    code_artifact_ref: str | None = None


T = TypeVar("T")


class DataPipelineController:
    """Runs all approved data operations; it never asks an Agent to execute."""

    def __init__(self, *, storage_root: Path, operator_executor: OperatorExecutor) -> None:
        self.storage_root = storage_root
        self.operator_executor = operator_executor
        self.processing_service = DataProcessingService()
        self.freeze_service = DataFreezeService()
        self.research_execution = ResearchAnalysisExecutionService(
            coding_provider=DeterministicTemplateCodingProvider(
                CodeArtifactStore(storage_root / "code-artifacts")
            ),
            output_root=storage_root / "research-execution-runs",
            execution_store=operator_executor.execution_store,
        )

    def begin(self, request: DataPipelineBeginRequest) -> DataPipelineState:
        if request.pre_analysis.readiness_report.status != "READY":
            raise ValueError("data pipeline requires a READY pre-analysis package")
        if request.pre_analysis.readiness_report.project_id != request.project_id:
            raise ValueError("pre-analysis project does not match data pipeline project")
        if request.model_specification.project_id != request.project_id:
            raise ValueError("model specification project does not match data pipeline project")
        if request.pre_analysis.executable_plan_candidate.preregistered_plan_ref != (
            request.preregistered_plan_ref
        ):
            raise ValueError("executable-plan candidate does not match preregistered plan")
        return DataPipelineState(
            project_id=request.project_id,
            stage=DataPipelineStage.WAITING_RAW_DATA,
            preregistered_plan_ref=request.preregistered_plan_ref,
            preregistration_approval_ref=request.preregistration_approval_ref,
            pre_analysis=request.pre_analysis,
            model_specification=request.model_specification,
            code_artifact_ref=request.code_artifact_ref,
        )

    def register_raw_csv(
        self, state: DataPipelineState, *, filename: str, content: bytes
    ) -> DataPipelineState:
        if state.stage is not DataPipelineStage.WAITING_RAW_DATA:
            raise ValueError("data pipeline is not accepting raw data")
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename or Path(safe_name).suffix.lower() != ".csv":
            raise ValueError("MVP accepts a safe CSV filename only")
        if not content:
            raise ValueError("raw CSV must not be empty")
        project_directory = self._project_directory(state.project_id)
        raw_directory = project_directory / "raw"
        raw_directory.mkdir(parents=True, exist_ok=True)
        content_hash = sha256_bytes(content)
        raw_path = raw_directory / f"{content_hash}.csv"
        raw_path.write_bytes(content)
        now = datetime.now(UTC)
        raw = RawDatasetRef(
            dataset_id=f"raw-{content_hash[:16]}",
            project_id=state.project_id,
            version=1,
            content_uri=str(raw_path),
            sha256=content_hash,
            raw_bytes_sha256=content_hash,
            canonical_content_sha256=self._canonical_hash_or_raw_hash(content),
            created_at=now,
        )
        audit = self._audit_raw_csv(state, raw)
        audit_gate = GateResult(
            gate_id="DataAuditGate",
            gate_version="mvp-csv-v1",
            project_id=state.project_id,
            artifact_id=raw.dataset_id,
            decision=GateDecision.PASS if audit.passed else GateDecision.REWORK,
            decision_scope=audit.decision_scope,
            blocked_target_ids=audit.blocked_target_ids,
            risk_flags=audit.risk_flags,
            missing_fields=audit.missing_required_variables,
            next_action=(
                "Request human approval for the processing plan."
                if audit.passed
                else "Return the raw-data artifact for correction."
            ),
            created_at=datetime.now(UTC),
        )
        if not audit.passed:
            return state.model_copy(
                update={
                    "stage": DataPipelineStage.REWORK,
                    "raw_dataset": raw,
                    "data_audit_report": audit,
                    "rework_reason": "Raw CSV failed the deterministic data audit.",
                    "blocked_target_ids": audit.blocked_target_ids,
                    "gate_results": [*state.gate_results, audit_gate],
                }
            )
        approval = DataPipelineApproval(
            request_id=f"data-approval-{uuid4().hex}",
            approval_type="data_processing",
            artifact_ref=f"processing-plan-candidate://{state.pre_analysis.agent_result.agent_run_id}",
            reason="Approve the data-processing plan before creating ProcessedDataset.",
        )
        return state.model_copy(
            update={
                "stage": DataPipelineStage.WAITING_PROCESSING_APPROVAL,
                "raw_dataset": raw,
                "data_audit_report": audit,
                "pending_approval": approval,
                "gate_results": [*state.gate_results, audit_gate],
            }
        )

    def decide(
        self, state: DataPipelineState, *, decision: str) -> DataPipelineState:
        approval = state.pending_approval
        if approval is None:
            raise ValueError("data pipeline has no pending human approval")
        if decision not in {"approved", "rejected"}:
            raise ValueError("data pipeline approval decision must be approved or rejected")
        if decision == "rejected":
            return state.model_copy(
                update={
                    "stage": DataPipelineStage.REWORK,
                    "pending_approval": None,
                    "rework_reason": f"{approval.approval_type} was rejected by human review.",
                    "blocked_target_ids": [approval.artifact_ref],
                }
            )
        if approval.approval_type == "data_processing":
            return self._process_approved_data(state)
        if approval.approval_type == "data_freeze":
            return self._freeze_approved_data(state)
        if approval.approval_type == "analysis_execution":
            return self._execute_approved_plan(state)
        raise ValueError(f"unsupported data pipeline approval type: {approval.approval_type}")

    def _process_approved_data(self, state: DataPipelineState) -> DataPipelineState:
        raw = self._require(state.raw_dataset, "raw dataset")
        processed = self.processing_service.process_csv_identity(
            raw_dataset=raw,
            processing_plan_ref=(
                f"processing-plan-candidate://{state.pre_analysis.agent_result.agent_run_id}"
            ),
            processing_approval_ref=self._require(state.pending_approval, "pending approval").request_id,
            destination_directory=self._project_directory(state.project_id) / "processed",
        )
        approval = DataPipelineApproval(
            request_id=f"data-approval-{uuid4().hex}",
            approval_type="data_freeze",
            artifact_ref=processed.ref,
            reason="Approve the processed data before creating FrozenDataset.",
        )
        return state.model_copy(
            update={
                "stage": DataPipelineStage.WAITING_FREEZE_APPROVAL,
                "processed_dataset": processed,
                "pending_approval": approval,
            }
        )

    def _freeze_approved_data(self, state: DataPipelineState) -> DataPipelineState:
        processed = self._require(state.processed_dataset, "processed dataset")
        frozen = self.freeze_service.freeze_csv(
            processed_dataset=processed,
            freeze_approval_ref=self._require(state.pending_approval, "pending approval").request_id,
            destination_directory=self._project_directory(state.project_id) / "frozen",
        )
        candidate = state.pre_analysis.executable_plan_candidate
        compatibility_gate = self._schema_compatibility_gate(state, frozen)
        if compatibility_gate.decision is GateDecision.REWORK:
            return state.model_copy(
                update={
                    "stage": DataPipelineStage.REWORK,
                    "frozen_dataset": frozen,
                    "pending_approval": None,
                    "rework_reason": "Frozen data schema is incompatible with the model specification.",
                    "blocked_target_ids": compatibility_gate.blocked_target_ids,
                    "gate_results": [*state.gate_results, compatibility_gate],
                }
            )
        executable_plan = ExecutableAnalysisPlan(
            executable_plan_id=f"executable-plan-{uuid4().hex}",
            project_id=state.project_id,
            preregistered_plan_ref=state.preregistered_plan_ref,
            frozen_dataset_ref=frozen.ref,
            frozen_dataset_sha256=frozen.sha256,
            dataset_schema_ref=frozen.schema_ref,
            variable_mapping=candidate.variable_mapping,
            type_confirmations=candidate.type_confirmations,
            software_configuration={
                **candidate.software_configuration,
                "engine": (
                    "python"
                    if candidate.analysis_mode.value == "PYTHON_ONLY"
                    else "spss_python_dual"
                ),
                "validation_mode": (
                    "SINGLE_ENGINE"
                    if candidate.analysis_mode.value == "PYTHON_ONLY"
                    else "CROSS_ENGINE"
                ),
            },
            analysis_mode=candidate.analysis_mode,
            model_specification_refs=candidate.model_specification_refs,
            compatibility_gate_ref=(
                f"gate://schema-compatibility/{frozen.schema_ref.rsplit('/', 1)[-1]}"
            ),
        )
        approval = DataPipelineApproval(
            request_id=f"data-approval-{uuid4().hex}",
            approval_type="analysis_execution",
            artifact_ref=f"executable-plan://{executable_plan.executable_plan_id}",
            reason="Approve the executable analysis plan and reviewed code before execution.",
        )
        return state.model_copy(
            update={
                "stage": DataPipelineStage.WAITING_EXECUTION_APPROVAL,
                "frozen_dataset": frozen,
                "executable_plan": executable_plan,
                "pending_approval": approval,
                "gate_results": [*state.gate_results, compatibility_gate],
            }
        )

    def _execute_approved_plan(self, state: DataPipelineState) -> DataPipelineState:
        frozen = self._require(state.frozen_dataset, "frozen dataset")
        executable_plan = self._require(state.executable_plan, "executable plan")
        execution = self.research_execution.execute_python_only(
            ResearchAnalysisExecutionRequest(
                project_id=state.project_id,
                frozen_dataset=frozen,
                executable_plan=executable_plan,
                model_specification=state.model_specification,
                execution_approval_ref=self._require(state.pending_approval, "pending approval").request_id,
            )
        )
        outcome = execution.sandbox_outcome
        if outcome.execution_run.status is not RunStatus.SUCCEEDED:
            return state.model_copy(
                update={
                    "stage": DataPipelineStage.BLOCKED,
                    "pending_approval": None,
                    "rework_reason": "Python execution was blocked or failed.",
                    "blocked_target_ids": [outcome.execution_run.operator_run_id],
                    "code_specification_ref": execution.code_specification.ref,
                    "code_artifact_ref": execution.code_artifact.ref,
                    "code_review_ref": execution.code_review.ref,
                }
            )
        validation = execution.validation_report
        if validation is None or not validation.passed:
            return state.model_copy(
                update={
                    "stage": DataPipelineStage.BLOCKED,
                    "pending_approval": None,
                    "validation_report": validation,
                    "rework_reason": "SINGLE_ENGINE result validation failed.",
                    "blocked_target_ids": [outcome.execution_run.operator_run_id],
                    "code_specification_ref": execution.code_specification.ref,
                    "code_artifact_ref": execution.code_artifact.ref,
                    "code_review_ref": execution.code_review.ref,
                }
            )
        result_card = self._require(execution.statistical_result_card, "statistical result card")
        return state.model_copy(
            update={
                "stage": DataPipelineStage.ANALYZED,
                "pending_approval": None,
                "validation_report": validation,
                "statistical_result_card": result_card,
                "code_specification_ref": execution.code_specification.ref,
                "code_artifact_ref": execution.code_artifact.ref,
                "code_review_ref": execution.code_review.ref,
            }
        )

    def _audit_raw_csv(self, state: DataPipelineState, raw: RawDatasetRef) -> DataAuditReport:
        missing_variables: list[str] = []
        risk_flags: list[str] = []
        try:
            with Path(raw.content_uri).open("r", encoding="utf-8", newline="") as source:
                header = next(csv.reader(source), [])
        except (OSError, UnicodeDecodeError, csv.Error):
            header = []
            risk_flags.append("RAW_CSV_UNREADABLE")
        required = set(state.pre_analysis.data_audit_specification.required_variables)
        missing_variables = sorted(required.difference(header))
        if missing_variables:
            risk_flags.append("REQUIRED_VARIABLES_MISSING")
        privacy_names = {"name", "email", "phone", "address", "id_number"}
        detected_privacy_columns = sorted(privacy_names.intersection({value.lower() for value in header}))
        if detected_privacy_columns:
            risk_flags.append("UNSANITIZED_DIRECT_IDENTIFIER")
        passed = not risk_flags
        return DataAuditReport(
            report_id=f"data-audit-report-{uuid4().hex}",
            project_id=state.project_id,
            raw_dataset_ref=raw.ref,
            passed=passed,
            missing_required_variables=missing_variables,
            risk_flags=risk_flags,
            decision_scope=DecisionScope.ARTIFACT if not passed else DecisionScope.TASK,
            blocked_target_ids=[raw.ref] if not passed else [],
            created_at=datetime.now(UTC),
        )

    def _schema_compatibility_gate(
        self, state: DataPipelineState, frozen: FrozenDatasetRef
    ) -> GateResult:
        try:
            with Path(frozen.content_uri).open("r", encoding="utf-8", newline="") as source:
                header = set(next(csv.reader(source), []))
        except (OSError, UnicodeDecodeError, csv.Error):
            header = set()
        required = {
            *state.model_specification.outcome_variables,
            *state.model_specification.predictor_variables,
            *state.model_specification.grouping_variables,
        }
        missing = sorted(required.difference(header))
        passed = not missing
        return GateResult(
            gate_id="SchemaCompatibilityGate",
            gate_version="mvp-csv-v1",
            project_id=state.project_id,
            artifact_id=frozen.dataset_id,
            decision=GateDecision.PASS if passed else GateDecision.REWORK,
            decision_scope=DecisionScope.ARTIFACT,
            blocked_target_ids=[] if passed else [frozen.ref],
            missing_fields=missing,
            next_action=(
                "Allow human approval of the executable analysis plan."
                if passed
                else "Return the executable analysis-plan candidate for schema correction."
            ),
            created_at=datetime.now(UTC),
        )

    def _project_directory(self, project_id: str) -> Path:
        return self.storage_root / "data-pipeline" / sha256_text(project_id)[:16]

    @staticmethod
    def _canonical_hash_or_raw_hash(content: bytes) -> str:
        """Keep the original bytes even when a malformed CSV must be reworked."""

        try:
            header, rows = read_csv_rows(content)
        except (UnicodeDecodeError, ValueError):
            return sha256_bytes(content)
        return sha256_bytes(canonical_csv_bytes(header, rows))

    @staticmethod
    def _require(value: T | None, label: str) -> T:
        if value is None:
            raise ValueError(f"data pipeline missing {label}")
        return value
