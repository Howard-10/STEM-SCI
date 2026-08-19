"""FastAPI surface for the STEM-SCI workflow platform."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agents import AgentCapability, ReviewFinding
from .agents.runtime import GPTProvider, StructuredGenerator
from .artifacts.artifact_store import SQLiteArtifactStore
from .artifacts.content_store import ArtifactContent, SQLiteArtifactContentStore
from .artifacts.execution_store import SQLiteExecutionStore
from .artifacts.models import ArtifactRef
from .context.models import (
    ApiError,
    ApiErrorResponse,
    ContextBuildRequest,
    ContextBundle,
    EvidenceDetail,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    SourceChunk,
    SourceDocument,
)
from .context.provider import LocalContextProvider
from .context.service import ContextInputError, ContextNotFoundError, ContextService
from .controller import (
    AgentDispatcher,
    AgentRegistry,
    ControllerWorkflowState,
    PlanningRequest,
    PlanningRunResult,
    ResearchController,
    SQLiteDecisionStore,
    SQLiteWorkflowStore,
    WorkflowRunResult,
)
from .controller.policy.route_decision import RouteDecision
from .controller.policy.route_store import SQLiteRouteDecisionStore
from .core.state import ResearchState
from .operators.executor import OperatorExecutor
from .operators.models import OperatorRun, OperatorSpec
from .operators.registry import OperatorRegistry
from .provenance.agent_run_store import SQLiteAgentRunStore
from .provenance.models import AgentRunRecord
from .provenance.tool_run_store import SQLiteToolRunStore
from .skills.builtin import BUILTIN_SKILLS
from .skills.registry import SkillRegistry
from .tools.gateway import ToolGateway
from .tools.models import ToolRunRecord
from .tools.registry import ToolRegistry

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _cors_origins() -> list[str]:
    configured = os.getenv("STEM_SCI_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _max_upload_bytes() -> int:
    configured = os.getenv("STEM_SCI_MAX_UPLOAD_BYTES")
    if configured is None:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(configured)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else DEFAULT_MAX_UPLOAD_BYTES


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
    )


app = FastAPI(title="STEM-SCI Research Workflow Platform", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
storage_root = Path(os.getenv("STEM_SCI_STORAGE_DIR", ".stem_sci"))
service = ContextService(storage_root, max_upload_bytes=_max_upload_bytes())
workflow_database = storage_root / "workflow.db"


def _configured_agent_registry() -> AgentRegistry:
    """Inject GPT pipelines only when a local API key explicitly enables them."""
    api_key = os.getenv("STEM_SCI_LLM_API_KEY", "")
    if not api_key.strip():
        return AgentRegistry.default()
    provider = GPTProvider.from_env()
    if not provider.default_model:
        raise ValueError("STEM_SCI_LLM_MODEL is required when GPT is enabled")
    return AgentRegistry.default(
        generator=StructuredGenerator(provider),
        model=provider.default_model,
    )


operator_registry = OperatorRegistry.default()
execution_store = SQLiteExecutionStore(workflow_database)
artifact_store = SQLiteArtifactStore(workflow_database)
artifact_content_store = SQLiteArtifactContentStore(workflow_database)
agent_run_store = SQLiteAgentRunStore(workflow_database)
tool_run_store = SQLiteToolRunStore(workflow_database)
route_store = SQLiteRouteDecisionStore(workflow_database)
workflow_controller = ResearchController(
    dispatcher=AgentDispatcher(_configured_agent_registry()),
    context_provider=LocalContextProvider(service),
    decision_store=SQLiteDecisionStore(workflow_database),
    workflow_store=SQLiteWorkflowStore(workflow_database),
    operator_executor=OperatorExecutor(
        registry=operator_registry,
        execution_store=execution_store,
    ),
    artifact_store=artifact_store,
    artifact_content_store=artifact_content_store,
    agent_run_store=agent_run_store,
    route_store=route_store,
    tool_gateway=ToolGateway(
        tool_registry=ToolRegistry.default(),
        skill_registry=SkillRegistry(BUILTIN_SKILLS),
        tool_run_store=tool_run_store,
        artifact_store=artifact_store,
        artifact_content_store=artifact_content_store,
        decision_store=SQLiteDecisionStore(workflow_database),
    ),
)


class WorkflowProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    research_intent: str = Field(min_length=1)
    context_bundle_ref: str = "context://initial"
    run_id: str | None = None


class WorkflowApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)


@app.exception_handler(ContextInputError)
async def handle_context_input(_: Request, error: ContextInputError) -> JSONResponse:
    return _error(400, error.code, str(error))


@app.exception_handler(ContextNotFoundError)
async def handle_not_found(_: Request, error: ContextNotFoundError) -> JSONResponse:
    return _error(404, "not_found", f"{error.resource} was not found")


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
    return _error(422, "invalid_request", "Request does not match the API contract")


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, error: StarletteHTTPException) -> JSONResponse:
    return _error(error.status_code, "http_error", "Request could not be completed")


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, __: Exception) -> JSONResponse:
    return _error(500, "internal_error", "An internal error occurred")


ProjectIdForm = Annotated[
    str,
    Form(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]
ProjectIdQuery = Annotated[
    str,
    Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/workflow/projects")
def create_workflow_project(request: WorkflowProjectRequest) -> PlanningRunResult:
    """Create a project and run the first planning slice."""
    return workflow_controller.start_planning(
        PlanningRequest(
            project_id=request.project_id,
            research_intent=request.research_intent,
            context_bundle_ref=request.context_bundle_ref,
            run_id=request.run_id or f"planning-{request.project_id}",
        )
    )


@app.get("/api/v1/workflow/projects/{project_id}")
def workflow_project(project_id: str) -> ControllerWorkflowState:
    return workflow_controller.get_state(project_id)


@app.post("/api/v1/workflow/projects/{project_id}/next")
def workflow_next(project_id: str) -> WorkflowRunResult:
    return workflow_controller.run_next(project_id)


@app.post("/api/v1/workflow/projects/{project_id}/approve")
def workflow_approve(project_id: str, request: WorkflowApprovalInput) -> ResearchState:
    approval = workflow_controller.get_pending_approval(project_id)
    return workflow_controller.resume_approval(
        project_id,
        approval,
        decision=request.decision,
        decided_by=request.decided_by,
    )


@app.get("/api/v1/workflow/agents")
def workflow_agents() -> list[AgentCapability]:
    return workflow_controller.list_agent_capabilities()


@app.get("/api/v1/workflow/operators")
def workflow_operators() -> list[OperatorSpec]:
    return operator_registry.list()


@app.get("/api/v1/workflow/projects/{project_id}/executions")
def workflow_executions(project_id: str) -> list[OperatorRun]:
    return execution_store.list_project(project_id)


@app.get("/api/v1/workflow/projects/{project_id}/artifacts")
def workflow_artifacts(project_id: str) -> list[ArtifactRef]:
    return artifact_store.list_project(project_id)


@app.get("/api/v1/workflow/projects/{project_id}/artifact-contents")
def workflow_artifact_contents(project_id: str) -> list[ArtifactContent]:
    return artifact_content_store.list_project(project_id)


@app.get("/api/v1/workflow/projects/{project_id}/agent-runs")
def workflow_agent_runs(project_id: str) -> list[AgentRunRecord]:
    return agent_run_store.list_project(project_id)


@app.get("/api/v1/workflow/projects/{project_id}/tool-runs")
def workflow_tool_runs(project_id: str) -> list[ToolRunRecord]:
    return tool_run_store.list_project(project_id)


@app.get("/api/v1/workflow/projects/{project_id}/routes")
def workflow_routes(project_id: str) -> list[RouteDecision]:
    return route_store.list_project(project_id)


@app.post("/api/v1/workflow/projects/{project_id}/review-findings")
def workflow_review_finding(project_id: str, finding: ReviewFinding) -> ResearchState:
    return workflow_controller.route_review_finding(project_id, finding)


@app.post("/api/v1/sources/import")
async def import_source(
    project_id: ProjectIdForm,
    file: Annotated[UploadFile, File(...)],
) -> SourceDocument:
    return service.import_bytes(project_id, file.filename or "upload.txt", await file.read())


@app.get("/api/v1/sources")
def sources(project_id: ProjectIdQuery) -> list[SourceDocument]:
    return service.list_sources(project_id)


@app.get("/api/v1/sources/{source_id}")
def source(source_id: str, project_id: ProjectIdQuery) -> SourceDocument:
    return service.get_source(project_id, source_id)


@app.get("/api/v1/sources/{source_id}/chunks")
def chunks(source_id: str, project_id: ProjectIdQuery) -> list[SourceChunk]:
    return service.chunks(project_id, source_id)


@app.post("/api/v1/evidence/search")
def search(request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
    return service.search(request)


@app.get("/api/v1/evidence/{evidence_id}")
def evidence(evidence_id: str, project_id: ProjectIdQuery) -> EvidenceDetail:
    return service.get_evidence(project_id, evidence_id)


def _reject_unknown_verification_parameters(request: Request) -> None:
    allowed = {"project_id", "verified_by", "verification_note"}
    unexpected = set(request.query_params).difference(allowed)
    if unexpected:
        raise ContextInputError(
            "unsupported_verification_parameter",
            "Verification accepts only project_id, verified_by, and verification_note",
        )


@app.post("/api/v1/evidence/{evidence_id}/verify-source")
def verify(
    evidence_id: str,
    project_id: ProjectIdQuery,
    verified_by: Annotated[str, Query(min_length=1)],
    verification_note: Annotated[str, Query(min_length=1)],
    request: Request,
) -> EvidenceRef:
    _reject_unknown_verification_parameters(request)
    return service.verify_source(project_id, evidence_id, verified_by, verification_note)


@app.post("/api/v1/context/build")
def build(request: ContextBuildRequest) -> ContextBundle:
    return service.build(request)


@app.get("/api/v1/context/{context_id}")
def context(context_id: str, project_id: ProjectIdQuery) -> ContextBundle:
    return service.get_bundle(project_id, context_id)
