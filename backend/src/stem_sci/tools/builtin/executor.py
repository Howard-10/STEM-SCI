"""Controller executor that dispatches structured requests to local Tools."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from stem_sci.agents.contracts import ToolRequest
from stem_sci.agents.evidence_pipeline.models import BoundedEvidenceSynthesis
from stem_sci.artifacts.artifact_store import ArtifactStore, InMemoryArtifactStore
from stem_sci.artifacts.content_store import ArtifactContentStore, InMemoryArtifactContentStore
from stem_sci.context.models import SourceChunk
from stem_sci.context.service import ContextService
from stem_sci.tools.models import ToolExecutionMode, ToolResult, ToolRunStatus, ToolSpec
from stem_sci.tools.policies import ToolPolicyError, validate_project_scope
from stem_sci.tools.sandbox import PythonExecutionRequest, PythonSandbox

from .analysis import PythonAnalysisSandboxTool
from .artifacts import ArtifactIntegrityCheckTool, ArtifactResolveTool
from .common import blocked
from .context import ContextBundleReadTool, EvidenceRefValidateTool
from .evidence import (
    BoundedSynthesisValidatorTool,
    CitationDeduplicatorTool,
    CorpusCoverageCalculatorTool,
    EvidenceConflictDetectorTool,
    EvidenceMatrixBuilderTool,
    KnowledgeBaseSearchTool,
    PaperCardExtractorTool,
    PaperScreeningExecutorTool,
    SourceChunkReaderTool,
    SourceVerificationCheckerTool,
)


class BuiltinToolExecutor:
    """Execute the registered local Tool using project-scoped dependencies."""

    def __init__(
        self,
        *,
        service: ContextService,
        project_root: Path,
        artifact_store: ArtifactStore | None = None,
        artifact_content_store: ArtifactContentStore | None = None,
    ) -> None:
        self.service = service
        self.project_root = project_root
        self.artifact_store = artifact_store or InMemoryArtifactStore()
        self.artifact_content_store = artifact_content_store or InMemoryArtifactContentStore()
        self._tools: dict[str, Callable[..., Any]] = {
            "context_bundle_read": ContextBundleReadTool(service).execute,
            "artifact_resolve": ArtifactResolveTool(self.artifact_content_store).execute,
            "artifact_integrity_check": ArtifactIntegrityCheckTool(self.artifact_content_store).execute,
            "evidence_ref_validate": EvidenceRefValidateTool(service).execute,
            "knowledge_base_search": KnowledgeBaseSearchTool(service).execute,
            "source_chunk_reader": SourceChunkReaderTool(service).execute,
            "source_verification_checker": SourceVerificationCheckerTool(service).execute,
            "paper_screening_executor": PaperScreeningExecutorTool(service).execute,
            "paper_card_extractor": PaperCardExtractorTool(service).execute,
            "evidence_matrix_builder": EvidenceMatrixBuilderTool(service).execute,
            "citation_deduplicator": CitationDeduplicatorTool().execute,
            "evidence_conflict_detector": EvidenceConflictDetectorTool(service).execute,
            "corpus_coverage_calculator": CorpusCoverageCalculatorTool(service).execute,
            "bounded_synthesis_validator": BoundedSynthesisValidatorTool(service).execute,
        }
        from . import analysis, research_design, review, writing

        for module in (analysis, research_design, review, writing):
            for tool_id in getattr(module, "__all__", ()):
                tool: Any = getattr(module, tool_id, None)
                if hasattr(tool, "execute"):
                    self._tools[tool_id] = tool.execute
        self._tools["python_analysis_sandbox"] = PythonAnalysisSandboxTool(
            PythonSandbox(project_root)
        ).execute

    def execute(
        self,
        spec: ToolSpec,
        project_id: str,
        agent_id: str,
        agent_run_id: str,
        request: ToolRequest,
    ) -> ToolResult:
        tool_fn = self._tools.get(spec.tool_id)
        if tool_fn is None:
            return ToolResult(
                tool_run_id="builtin-missing",
                project_id=project_id,
                tool_id=spec.tool_id,
                tool_version=spec.tool_version,
                status=ToolRunStatus.BLOCKED,
                error_code="TOOL_EXECUTOR_UNAVAILABLE",
            )
        try:
            value = self._call(tool_fn, project_id, request.input_payload, request)
        except (KeyError, TypeError, ValueError) as error:
            return ToolResult(
                tool_run_id="builtin-error",
                project_id=project_id,
                tool_id=spec.tool_id,
                tool_version=spec.tool_version,
                status=ToolRunStatus.FAILED,
                error_code=(
                    str(error)
                    if str(error)
                    in {"INVALID_INPUT", "REFERENCE_NOT_FOUND", "PROJECT_SCOPE_VIOLATION"}
                    else "EXECUTION_FAILED"
                ),
            )
        if hasattr(value, "status"):
            status = value.status
            error_code = value.error_code
            payload = value.value
        else:
            status, error_code, payload = ToolRunStatus.SUCCEEDED, None, value
        output_data = self._dump(payload)
        output_payloads = []
        if (
            status is ToolRunStatus.SUCCEEDED
            and spec.execution_mode is ToolExecutionMode.CANDIDATE_OUTPUT
            and output_data is not None
        ):
            try:
                output_payloads = [
                    self._candidate_payload(spec, project_id, request, output_data)
                ]
            except ToolPolicyError as error:
                return ToolResult(
                    tool_run_id="builtin-result",
                    project_id=project_id,
                    tool_id=spec.tool_id,
                    tool_version=spec.tool_version,
                    status=ToolRunStatus.BLOCKED,
                    error_code=error.error_code,
                )
            except ValueError as error:
                return ToolResult(
                    tool_run_id="builtin-result",
                    project_id=project_id,
                    tool_id=spec.tool_id,
                    tool_version=spec.tool_version,
                    status=ToolRunStatus.BLOCKED,
                    error_code=str(error) if str(error) == "PROJECT_SCOPE_VIOLATION" else "EXECUTION_FAILED",
                )
        return ToolResult(
            tool_run_id="builtin-result",
            project_id=project_id,
            tool_id=spec.tool_id,
            tool_version=spec.tool_version,
            status=status,
            error_code=error_code,
            output_data=output_data,
            output_payloads=output_payloads,
        )

    @staticmethod
    def _candidate_payload(
        spec: ToolSpec,
        project_id: str,
        request: ToolRequest,
        body: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        BuiltinToolExecutor._validate_embedded_project_scope(project_id, body)
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        artifact_type = body.get("output_type")
        return {
            "project_id": project_id,
            "artifact_id": (
                f"tool-{spec.tool_id}-"
                f"{hashlib.sha256(request.request_id.encode()).hexdigest()[:16]}"
            ),
            "version": 1,
            "artifact_type": (
                artifact_type if isinstance(artifact_type, str) else f"{spec.tool_id}Candidate"
            ),
            "schema_ref": spec.output_schema_ref,
            "schema_version": spec.tool_version,
            "body": body,
            "content_hash": hashlib.sha256(canonical.encode()).hexdigest(),
        }

    @staticmethod
    def _validate_embedded_project_scope(project_id: str, value: Any) -> None:
        if isinstance(value, dict):
            embedded = value.get("project_id")
            if embedded is not None and embedded != project_id:
                raise ValueError("PROJECT_SCOPE_VIOLATION")
            for item in value.values():
                BuiltinToolExecutor._validate_embedded_project_scope(project_id, item)
        elif isinstance(value, list):
            for item in value:
                BuiltinToolExecutor._validate_embedded_project_scope(project_id, item)
        elif isinstance(value, str) and value.startswith(
            ("artifact://", "artifact-content://", "source://", "context://", "evidence://")
        ):
            validate_project_scope(project_id, [value], allow_initial_context=True)

    def _call(
        self, tool: Callable[..., Any], project_id: str, payload: dict[str, JsonValue], request: ToolRequest
    ) -> Any:
        data = dict(payload)
        name = getattr(tool, "__qualname__", "")
        if "PythonAnalysisSandboxTool" in name:
            raw_request = data.get("request")
            if not isinstance(raw_request, dict):
                raise TypeError("INVALID_INPUT")
            execution_request = PythonExecutionRequest.model_validate(raw_request)
            if execution_request.project_id != project_id:
                return blocked("PROJECT_SCOPE_VIOLATION")
            return tool(execution_request)
        if "ContextBundleReadTool" in name:
            return tool(project_id, self._string(data.get("context_id")))
        if "ArtifactResolveTool" in name or "ArtifactIntegrityCheckTool" in name:
            return tool(project_id, self._string(data.get("artifact_ref") or (request.input_refs[0] if request.input_refs else None)))
        if "EvidenceRefValidateTool" in name:
            return tool(project_id, self._string(data.get("evidence_id")))
        if "KnowledgeBaseSearchTool" in name:
            return tool(project_id, self._string(data.get("query")), int(self._number(data.get("limit", 10))))
        if "SourceChunkReaderTool" in name:
            return tool(project_id, self._string(data.get("source_id")), self._list(data.get("chunk_ids")))
        if "SourceVerificationCheckerTool" in name:
            refs = [self.service.get_evidence(project_id, self._string(item)) for item in self._list(data.get("evidence_refs"))]
            return tool(project_id, refs)
        if "PaperScreeningExecutorTool" in name:
            return tool(project_id, self._list(data.get("source_refs")), self._list(data.get("criteria")))
        if "PaperCardExtractorTool" in name:
            chunks = [SourceChunk.model_validate(item) for item in self._list(data.get("source_chunks"))]
            return tool(project_id, chunks)
        if "EvidenceMatrixBuilderTool" in name:
            return tool(project_id, self._list(data.get("paper_cards")))
        if "BoundedSynthesisValidatorTool" in name:
            return tool(project_id, BoundedEvidenceSynthesis.model_validate(data["synthesis"]))
        return tool(project_id, **data)

    @staticmethod
    def _dump(value: Any) -> dict[str, JsonValue] | None:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        if isinstance(value, bool):
            return {"integrity_ok": value}
        if isinstance(value, list):
            return {"items": value}
        return {"value": value}

    @staticmethod
    def _string(value: JsonValue) -> str:
        if not isinstance(value, str) or not value:
            raise TypeError("INVALID_INPUT")
        return value

    @staticmethod
    def _number(value: JsonValue) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("INVALID_INPUT")
        return value

    @staticmethod
    def _list(value: JsonValue) -> list[Any]:
        if not isinstance(value, list):
            raise TypeError("INVALID_INPUT")
        return value


__all__ = ["BuiltinToolExecutor"]
