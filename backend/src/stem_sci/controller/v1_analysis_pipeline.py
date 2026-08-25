"""Controller-owned orchestration for the frozen v1.0 statistics chain.

This module deliberately has no Agent calls and does not mutate a project's
``current_stage``.  It creates deterministic artifacts and returns the
Controller-facing route facts needed by a future workflow transition.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from typing import Literal

from pydantic import Field

from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.coding.compiler import CodeSpecificationCompiler
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.providers import (
    CodeArtifactStore,
    CodeGenerationRequest,
    DeterministicStatsmodelsTemplateProvider,
)
from stem_sci.coding.review import CodeReviewGate, CodeReviewResult
from stem_sci.core.enums import GateDecision, RunStatus
from stem_sci.core.models import DomainModel, GateResult
from stem_sci.research_data.analysis_dataset import DeterministicDataProcessor
from stem_sci.research_data.audit import (
    ModelEligibilityEvaluator,
    StructuralDataAuditReport,
    StructuralDataAuditor,
    structural_gate,
)
from stem_sci.research_data.models import (
    AnalysisDatasetRef,
    FrozenDatasetRef,
    ModelEligibilityManifest,
    ParticipantEligibilityManifest,
)
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    HumanExecutionApproval,
    StatisticalResultCard,
)
from stem_sci.statistics.v1_execution import (
    DeterministicStatsmodelsExecutor,
    V1ExecutionOutcome,
    V1ExecutionRequest,
)
from stem_sci.utils.hash_utils import sha256_text


class V1AnalysisPreparationRequest(DomainModel):
    """Inputs already approved before the Controller prepares one model run."""

    project_id: str = Field(min_length=1)
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    executable_plan_sha256: str = Field(min_length=64, max_length=64)
    model_specification: AnalysisModelSpecification
    data_processing_plan_ref: str = Field(min_length=1)
    analysis_dataset_specification_ref: str = Field(min_length=1)
    environment_spec_sha256: str = Field(min_length=64, max_length=64)
    minimum_group_size: int = Field(default=24, ge=1)
    minimum_group_sequence_size: int = Field(default=12, ge=1)


class V1PreparedAnalysis(DomainModel):
    """Immutable package awaiting an exact HumanExecutionApproval."""

    structural_audit: StructuralDataAuditReport
    structural_gate: GateResult
    participant_eligibility: ParticipantEligibilityManifest | None = None
    model_eligibility: ModelEligibilityManifest | None = None
    analysis_dataset: AnalysisDatasetRef | None = None
    code_specification: CodeSpecification | None = None
    code_artifact: CodeArtifact | None = None
    code_review: CodeReviewResult | None = None
    blocked: bool = False
    blocked_reason: str | None = None


class V1AnalysisExecutionResult(DomainModel):
    """Determinstic execution records; no agent-generated result values."""

    prepared: V1PreparedAnalysis
    execution_outcome: V1ExecutionOutcome | None = None
    statistical_result_card: StatisticalResultCard | None = None
    next_route: str = "WAITING_HUMAN"
    route_reason: str = "Awaiting exact HumanExecutionApproval."


class V1AnalysisPipelineController:
    """Prepare, bind, and execute one frozen v1.0 statistics model.

    This service owns *operator* invocation.  It only accepts precompiled
    plans and frozen data; it never changes model semantics or study state.
    A caller must separately record the resulting route as ``WAITING_HUMAN``
    when the package is awaiting approval or when validation fails.
    """

    _model_ids = {
        "linear_mixed_effects_primary": "primary_lmm",
        "ols_ancova_transfer": "transfer_ancova",
        "linear_mixed_effects_prompt_dependency": "prompt_dependency_lmm",
    }
    template_version = DeterministicStatsmodelsExecutor.template_version

    def __init__(
        self,
        *,
        artifact_root: Path,
        output_root: Path,
        execution_store: ExecutionStore | None = None,
        auditor: StructuralDataAuditor | None = None,
        eligibility_evaluator: ModelEligibilityEvaluator | None = None,
        data_processor: DeterministicDataProcessor | None = None,
        compiler: CodeSpecificationCompiler | None = None,
        code_review_gate: CodeReviewGate | None = None,
        executor: DeterministicStatsmodelsExecutor | None = None,
    ) -> None:
        self.artifact_root = artifact_root
        self.output_root = output_root
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.auditor = auditor or StructuralDataAuditor()
        self.eligibility_evaluator = eligibility_evaluator or ModelEligibilityEvaluator()
        self.data_processor = data_processor or DeterministicDataProcessor()
        self.compiler = compiler or CodeSpecificationCompiler()
        self.code_review_gate = code_review_gate or CodeReviewGate()
        self.executor = executor or DeterministicStatsmodelsExecutor()

    def prepare(self, request: V1AnalysisPreparationRequest) -> V1PreparedAnalysis:
        """Create only deterministic artifacts; no execution occurs here."""

        self._validate_scope(request)
        audit = self.auditor.audit(request.frozen_dataset)
        audit_gate = structural_gate(audit)
        if not audit.passed or audit.participant_eligibility_manifest is None:
            return V1PreparedAnalysis(
                structural_audit=audit,
                structural_gate=audit_gate,
                blocked=True,
                blocked_reason="STRUCTURAL_DATA_AUDIT_FAILED",
            )
        model_id = self._model_ids.get(request.model_specification.model_family)
        if model_id is None:
            raise ValueError("unsupported v1.0 deterministic model family")
        eligibility = self.eligibility_evaluator.evaluate(
            frozen_dataset=request.frozen_dataset,
            participant_manifest=audit.participant_eligibility_manifest,
            model_id=model_id,
            minimum_group_size=request.minimum_group_size,
            minimum_group_sequence_size=request.minimum_group_sequence_size,
        )
        if not eligibility.passed_minimum_coverage:
            return V1PreparedAnalysis(
                structural_audit=audit,
                structural_gate=audit_gate,
                participant_eligibility=audit.participant_eligibility_manifest,
                model_eligibility=eligibility,
                blocked=True,
                blocked_reason="MODEL_ELIGIBILITY_MINIMUM_COVERAGE_FAILED",
            )
        analysis_dataset = self.data_processor.create_analysis_dataset(
            frozen_dataset=request.frozen_dataset,
            participant_manifest=audit.participant_eligibility_manifest,
            model_manifest=eligibility,
            data_processing_plan_ref=request.data_processing_plan_ref,
            analysis_dataset_specification_ref=request.analysis_dataset_specification_ref,
            model_specification_ref=f"model-spec://{request.model_specification.model_spec_id}",
            destination_directory=self.artifact_root / "analysis-datasets",
        )
        specification = self.compiler.compile_v1_statsmodels(
            specification_id=f"code-spec-{uuid4().hex}",
            executable_plan=request.executable_plan,
            frozen_dataset=request.frozen_dataset,
            analysis_dataset=analysis_dataset,
            model_specification=request.model_specification,
        )
        artifact = DeterministicStatsmodelsTemplateProvider(
            CodeArtifactStore(self.artifact_root / "code-artifacts")
        ).generate(CodeGenerationRequest(project_id=request.project_id, specification=specification))
        review = self.code_review_gate.review(
            review_id=f"code-review-{uuid4().hex}", specification=specification, artifact=artifact
        )
        return V1PreparedAnalysis(
            structural_audit=audit,
            structural_gate=audit_gate,
            participant_eligibility=audit.participant_eligibility_manifest,
            model_eligibility=eligibility,
            analysis_dataset=analysis_dataset,
            code_specification=specification,
            code_artifact=artifact,
            code_review=review,
            blocked=review.gate_result.decision is not GateDecision.PASS,
            blocked_reason=None if review.gate_result.decision is GateDecision.PASS else "CODE_REVIEW_FAILED",
        )

    def approve_execution(
        self,
        *,
        request: V1AnalysisPreparationRequest,
        prepared: V1PreparedAnalysis,
        approved_by: str,
        approval_status: Literal["approved", "rejected"] = "approved",
    ) -> HumanExecutionApproval:
        """Bind one explicit human decision to all content-addressed inputs."""

        if prepared.blocked:
            raise ValueError("a blocked package cannot receive execution approval")
        specification, artifact, review, dataset = self._required_package(prepared)
        return HumanExecutionApproval(
            approval_id=f"human-execution-approval-{uuid4().hex}",
            project_id=request.project_id,
            approved_at=datetime.now(UTC),
            approved_by=approved_by,
            approval_status=approval_status,
            plan_sha256=request.executable_plan_sha256,
            code_spec_sha256=sha256_text(specification.model_dump_json(exclude_none=True)),
            code_artifact_sha256=artifact.sha256,
            code_review_result_sha256=sha256_text(review.model_dump_json(exclude_none=True)),
            analysis_dataset_sha256=dataset.canonical_content_sha256,
            environment_spec_sha256=request.environment_spec_sha256,
            template_version=self.template_version,
        )

    def execute(
        self,
        *,
        request: V1AnalysisPreparationRequest,
        prepared: V1PreparedAnalysis,
        approval: HumanExecutionApproval,
    ) -> V1AnalysisExecutionResult:
        """Run only an exact, approved deterministic package."""

        if prepared.blocked:
            return V1AnalysisExecutionResult(prepared=prepared)
        specification, artifact, review, dataset = self._required_package(prepared)
        outcome = self.executor.execute(
            V1ExecutionRequest(
                project_id=request.project_id,
                frozen_dataset=request.frozen_dataset,
                analysis_dataset=dataset,
                executable_plan=request.executable_plan,
                executable_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
                executable_plan_sha256=request.executable_plan_sha256,
                model_specification=request.model_specification,
                code_specification=specification,
                code_artifact=artifact,
                code_review=review,
                human_execution_approval=approval,
                environment_spec_sha256=request.environment_spec_sha256,
            ),
            self.output_root,
        )
        self.execution_store.put(outcome.execution_run)
        if (
            outcome.execution_run.status is not RunStatus.SUCCEEDED
            or outcome.validation_report is None
            or not outcome.validation_report.passed
        ):
            return V1AnalysisExecutionResult(
                prepared=prepared,
                execution_outcome=outcome,
                next_route="WAITING_HUMAN",
                route_reason="Execution or deterministic result validation requires human review.",
            )
        result_card = StatisticalResultCard.build_from_validation(
            result_id=f"result-card-{uuid4().hex}",
            project_id=request.project_id,
            execution_run_ref=outcome.execution_run.operator_run_id,
            analysis_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
            validation_report=outcome.validation_report,
            parsed_values=outcome.result_values,
            deterministic_parser_version="statsmodels-result-v1",
        )
        return V1AnalysisExecutionResult(
            prepared=prepared,
            execution_outcome=outcome,
            statistical_result_card=result_card,
            next_route="WAITING_HUMAN",
            route_reason="Validated result card is ready for independent review and human interpretation approval.",
        )

    @staticmethod
    def _required_package(
        prepared: V1PreparedAnalysis,
    ) -> tuple[CodeSpecification, CodeArtifact, CodeReviewResult, AnalysisDatasetRef]:
        if (
            prepared.code_specification is None
            or prepared.code_artifact is None
            or prepared.code_review is None
            or prepared.analysis_dataset is None
        ):
            raise ValueError("prepared analysis package is incomplete")
        return (
            prepared.code_specification,
            prepared.code_artifact,
            prepared.code_review,
            prepared.analysis_dataset,
        )

    @staticmethod
    def _validate_scope(request: V1AnalysisPreparationRequest) -> None:
        if request.frozen_dataset.project_id != request.project_id:
            raise ValueError("frozen dataset project scope mismatch")
        if request.executable_plan.project_id != request.project_id:
            raise ValueError("executable plan project scope mismatch")
        if request.model_specification.project_id != request.project_id:
            raise ValueError("model specification project scope mismatch")
        if request.executable_plan.frozen_dataset_ref != request.frozen_dataset.ref:
            raise ValueError("executable plan frozen-dataset reference mismatch")
        if request.executable_plan.frozen_dataset_sha256 != request.frozen_dataset.canonical_content_sha256:
            raise ValueError("executable plan frozen-dataset hash mismatch")
        actual_plan_hash = sha256_text(request.executable_plan.model_dump_json(exclude_none=True))
        if request.executable_plan_sha256 != actual_plan_hash:
            raise ValueError("executable plan content hash mismatch")
