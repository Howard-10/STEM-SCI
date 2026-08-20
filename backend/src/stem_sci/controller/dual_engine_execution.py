"""Controller-owned Python/SPSS dual-engine execution for the narrow MVP.

This service deliberately supports the same bounded ``group_mean_difference``
contract as the existing adapters.  It never downgrades a dual plan when SPSS
is unavailable, and it creates a result card only after both engines agree.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import Field

from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.providers import (
    CodeArtifactStore,
    CodeGenerationRequest,
    CodingProvider,
    DeterministicTemplateCodingProvider,
)
from stem_sci.coding.review import CodeReviewResult
from stem_sci.controller.analysis_execution import (
    ResearchAnalysisExecutionRequest,
    ResearchAnalysisExecutionResult,
    ResearchAnalysisExecutionService,
)
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.statistics.dual_validation import (
    CrossEngineResultValidator,
    DualEngineValidationOutcome,
)
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    ResultValidationReport,
    StatisticalResultCard,
)
from stem_sci.statistics.spss_adapter import (
    SpssAdapter,
    SpssAnalysisRequest,
    SpssExecutionOutcome,
)
from stem_sci.statistics.spss_syntax import (
    SpssSyntaxSpecificationCompiler,
    SpssSyntaxTemplateProvider,
)
from stem_sci.statistics.python_operator import PythonExecutionOutcome


class DualEngineExecutionRequest(DomainModel):
    project_id: str = Field(min_length=1)
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    model_specification: AnalysisModelSpecification
    execution_approval_ref: str = Field(min_length=1)
    code_human_approval_ref: str | None = None
    # SPSS and Python may use different summation order and variance
    # implementations; retain a strict but practical relative tolerance.
    tolerance: float = Field(default=1e-7, ge=0.0)


class DualEngineExecutionResult(DomainModel):
    python_code_specification: CodeSpecification
    python_code_artifact: CodeArtifact
    python_code_review: CodeReviewResult
    spss_code_specification: CodeSpecification | None = None
    spss_code_artifact: CodeArtifact | None = None
    spss_execution: SpssExecutionOutcome | None = None
    python_execution: PythonExecutionOutcome | None = None
    consistency: DualEngineValidationOutcome | None = None
    validation_report: ResultValidationReport | None = None
    statistical_result_card: StatisticalResultCard | None = None


class DualEngineExecutionService:
    """Run both engines against one exact frozen dataset and compare outputs."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        output_root: Path,
        coding_provider: CodingProvider | None = None,
        spss_adapter: SpssAdapter | None = None,
        execution_store: ExecutionStore | None = None,
    ) -> None:
        self.artifact_root = artifact_root
        self.output_root = output_root
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.coding_provider = coding_provider or DeterministicTemplateCodingProvider(
            CodeArtifactStore(artifact_root / "python")
        )
        self.python_service = ResearchAnalysisExecutionService(
            coding_provider=self.coding_provider,
            output_root=output_root / "python",
            execution_store=self.execution_store,
        )
        self.spss_adapter = spss_adapter or SpssAdapter()
        self.spss_syntax_compiler = SpssSyntaxSpecificationCompiler()
        self.spss_artifact_store = CodeArtifactStore(artifact_root / "spss")

    def execute(self, request: DualEngineExecutionRequest) -> DualEngineExecutionResult:
        self._validate_request(request)

        python_plan = request.executable_plan.model_copy(
            update={"analysis_mode": AnalysisMode.PYTHON_ONLY}
        )
        python_result = self.python_service.execute_python_only(
            ResearchAnalysisExecutionRequest(
                project_id=request.project_id,
                frozen_dataset=request.frozen_dataset,
                executable_plan=python_plan,
                model_specification=request.model_specification,
                execution_approval_ref=request.execution_approval_ref,
                code_human_approval_ref=request.code_human_approval_ref,
            )
        )
        python_outcome = self._python_outcome(request, python_result)
        result = DualEngineExecutionResult(
            python_code_specification=python_result.code_specification,
            python_code_artifact=python_result.code_artifact,
            python_code_review=python_result.code_review,
            python_execution=python_outcome,
        )
        if python_outcome.execution_run.status is not RunStatus.SUCCEEDED:
            return result

        spss_spec = self.spss_syntax_compiler.compile(
            specification_id=f"spss-spec-{uuid4().hex}",
            executable_plan=request.executable_plan,
            frozen_dataset=request.frozen_dataset,
            model_specification=request.model_specification,
        )
        spss_artifact = SpssSyntaxTemplateProvider(self.spss_artifact_store).generate(
            CodeGenerationRequest(project_id=request.project_id, specification=spss_spec)
        )
        spss_review_ref = f"spss-review://{spss_artifact.artifact_id}"
        spss_outcome = self.spss_adapter.execute(
            SpssAnalysisRequest(
                project_id=request.project_id,
                frozen_dataset=request.frozen_dataset,
                executable_plan=request.executable_plan,
                model_specification=request.model_specification,
                syntax_artifact=spss_artifact,
                syntax_review_ref=spss_review_ref,
            ),
            self.output_root / "spss",
        )
        result = result.model_copy(
            update={
                "spss_code_specification": spss_spec,
                "spss_code_artifact": spss_artifact,
                "spss_execution": spss_outcome,
            }
        )
        if spss_outcome.execution_run.status is not RunStatus.SUCCEEDED:
            return result

        consistency = CrossEngineResultValidator().validate(
            report_id=f"result-validation-{uuid4().hex}",
            consistency_report_id=f"result-consistency-{uuid4().hex}",
            python_outcome=python_outcome,
            spss_outcome=spss_outcome,
            tolerance=request.tolerance,
        )
        result = result.model_copy(
            update={"consistency": consistency, "validation_report": consistency.validation_report}
        )
        if consistency.validation_report.passed:
            result = result.model_copy(
                update={
                    "statistical_result_card": StatisticalResultCard.build_from_validation(
                        result_id=f"result-card-{uuid4().hex}",
                        project_id=request.project_id,
                        execution_run_ref=python_outcome.execution_run.operator_run_id,
                        analysis_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
                        validation_report=consistency.validation_report,
                        parsed_values=python_outcome.result_values,
                        deterministic_parser_version="dual-engine-result-v1",
                    )
                }
            )
        return result

    @staticmethod
    def _validate_request(request: DualEngineExecutionRequest) -> None:
        if request.executable_plan.analysis_mode is not AnalysisMode.SPSS_PYTHON_DUAL:
            raise ValueError("dual-engine execution requires SPSS_PYTHON_DUAL")
        if request.frozen_dataset.project_id != request.project_id:
            raise ValueError("frozen dataset project does not match execution project")
        if request.executable_plan.project_id != request.project_id:
            raise ValueError("executable plan project does not match execution project")
        if request.model_specification.project_id != request.project_id:
            raise ValueError("model specification project does not match execution project")
        if request.executable_plan.frozen_dataset_ref != request.frozen_dataset.ref:
            raise ValueError("executable plan references a different frozen dataset")
        if request.executable_plan.frozen_dataset_sha256 != request.frozen_dataset.sha256:
            raise ValueError("executable plan frozen-dataset hash does not match")

    @staticmethod
    def _python_outcome(
        request: DualEngineExecutionRequest,
        result: ResearchAnalysisExecutionResult,
    ) -> PythonExecutionOutcome:
        execution = result.sandbox_outcome
        return PythonExecutionOutcome(
            execution_run=execution.execution_run,
            frozen_dataset=request.frozen_dataset,
            executable_plan=request.executable_plan,
            model_specification=request.model_specification,
            result_values=execution.result_values,
            result_payload_sha256=execution.result_payload_sha256,
        )
