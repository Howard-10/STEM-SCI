"""Controller-owned, traceable research-code execution service.

This service does not advance ``ResearchState.current_stage``.  It is a
deterministic operation invoked by a future Controller transition after the
required approvals have already been recorded.  Agents neither call it nor
receive permission to change any artifact it creates.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import Field

from stem_sci.artifacts.execution_store import ExecutionStore, InMemoryExecutionStore
from stem_sci.coding.compiler import CodeSpecificationCompiler
from stem_sci.coding.models import CodeArtifact, CodeSpecification
from stem_sci.coding.providers import CodeGenerationRequest, CodingProvider
from stem_sci.coding.review import CodeReviewGate, CodeReviewResult
from stem_sci.coding.sandbox import ResearchCodeSandbox, SandboxExecutionOutcome
from stem_sci.core.enums import RunStatus
from stem_sci.core.models import DomainModel
from stem_sci.research_data.models import FrozenDatasetRef
from stem_sci.statistics.mode_policy import AnalysisMode
from stem_sci.statistics.models import (
    AnalysisModelSpecification,
    ExecutableAnalysisPlan,
    ResultValidationReport,
    StatisticalResultCard,
)
from stem_sci.statistics.python_operator import PythonExecutionOutcome
from stem_sci.statistics.validation import SingleEngineResultValidator


class ResearchAnalysisExecutionRequest(DomainModel):
    project_id: str = Field(min_length=1)
    frozen_dataset: FrozenDatasetRef
    executable_plan: ExecutableAnalysisPlan
    model_specification: AnalysisModelSpecification
    execution_approval_ref: str = Field(min_length=1)
    code_human_approval_ref: str | None = None


class ResearchAnalysisExecutionResult(DomainModel):
    """All deterministic artifacts from one Python-only execution attempt."""

    code_specification: CodeSpecification
    code_artifact: CodeArtifact
    code_review: CodeReviewResult
    sandbox_outcome: SandboxExecutionOutcome
    validation_report: ResultValidationReport | None = None
    statistical_result_card: StatisticalResultCard | None = None


class ResearchAnalysisExecutionService:
    """Build, review and execute an approved Python-only analysis artifact."""

    def __init__(
        self,
        *,
        coding_provider: CodingProvider,
        output_root: Path,
        execution_store: ExecutionStore | None = None,
        compiler: CodeSpecificationCompiler | None = None,
        code_review_gate: CodeReviewGate | None = None,
        sandbox: ResearchCodeSandbox | None = None,
        result_validator: SingleEngineResultValidator | None = None,
    ) -> None:
        self.coding_provider = coding_provider
        self.output_root = output_root
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.compiler = compiler or CodeSpecificationCompiler()
        self.code_review_gate = code_review_gate or CodeReviewGate()
        self.sandbox = sandbox or ResearchCodeSandbox()
        self.result_validator = result_validator or SingleEngineResultValidator(
            freeze_service=self.sandbox.freeze_service
        )

    def execute_python_only(
        self, request: ResearchAnalysisExecutionRequest
    ) -> ResearchAnalysisExecutionResult:
        """Run the actual MVP chain after a Controller-owned approval.

        A dual-engine plan is intentionally rejected here.  Downgrading a
        preregistered dual plan to Python-only would be a substantive workflow
        decision, not an implementation convenience.
        """

        if request.executable_plan.analysis_mode is not AnalysisMode.PYTHON_ONLY:
            raise ValueError("dual-engine plans require the SPSS/Python execution service")
        specification = self.compiler.compile_python(
            specification_id=f"code-spec-{uuid4().hex}",
            executable_plan=request.executable_plan,
            frozen_dataset=request.frozen_dataset,
            model_specification=request.model_specification,
        )
        artifact = self.coding_provider.generate(
            CodeGenerationRequest(project_id=request.project_id, specification=specification)
        )
        review = self.code_review_gate.review(
            review_id=f"code-review-{uuid4().hex}", specification=specification, artifact=artifact
        )
        sandbox_outcome = self.sandbox.execute(
            project_id=request.project_id,
            frozen_dataset=request.frozen_dataset,
            specification=specification,
            artifact=artifact,
            review=review,
            output_root=self.output_root,
            human_approval_ref=request.code_human_approval_ref,
        )
        self.execution_store.put(sandbox_outcome.execution_run)
        if sandbox_outcome.execution_run.status is not RunStatus.SUCCEEDED:
            return ResearchAnalysisExecutionResult(
                code_specification=specification,
                code_artifact=artifact,
                code_review=review,
                sandbox_outcome=sandbox_outcome,
            )
        python_outcome = PythonExecutionOutcome(
            execution_run=sandbox_outcome.execution_run,
            frozen_dataset=request.frozen_dataset,
            executable_plan=request.executable_plan,
            model_specification=request.model_specification,
            result_values=sandbox_outcome.result_values,
            result_payload_sha256=sandbox_outcome.result_payload_sha256,
        )
        validation = self.result_validator.validate(
            python_outcome, report_id=f"result-validation-{uuid4().hex}"
        )
        if not validation.passed:
            return ResearchAnalysisExecutionResult(
                code_specification=specification,
                code_artifact=artifact,
                code_review=review,
                sandbox_outcome=sandbox_outcome,
                validation_report=validation,
            )
        result_card = StatisticalResultCard.build_from_validation(
            result_id=f"result-card-{uuid4().hex}",
            project_id=request.project_id,
            execution_run_ref=sandbox_outcome.execution_run.operator_run_id,
            analysis_plan_ref=f"executable-plan://{request.executable_plan.executable_plan_id}",
            validation_report=validation,
            parsed_values=sandbox_outcome.result_values,
            deterministic_parser_version="research-python-result-v1",
        )
        return ResearchAnalysisExecutionResult(
            code_specification=specification,
            code_artifact=artifact,
            code_review=review,
            sandbox_outcome=sandbox_outcome,
            validation_report=validation,
            statistical_result_card=result_card,
        )
