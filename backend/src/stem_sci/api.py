"""FastAPI surface for the STEM-SCI workflow platform."""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from xml.etree import ElementTree

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader
from starlette.exceptions import HTTPException as StarletteHTTPException

from .accounts import (
    AuthError,
    AuthTokenPair,
    IdentityService,
    LoginRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ResearchProject,
    TokenRefreshRequest,
    UserCreateRequest,
    UserProfile,
)
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
from .context.provider import HybridContextProvider, LocalContextProvider
from .context.service import ContextInputError, ContextNotFoundError, ContextService
from .controller import (
    AgentDispatcher,
    AgentRegistry,
    ControllerWorkflowState,
    DataPipelineBeginRequest,
    DataPipelineState,
    PlanningRequest,
    PlanningRunResult,
    ReproducibilityReviewRequest,
    ReproducibilityReviewRunResult,
    ResearchController,
    WorkflowFeedbackResult,
    SQLiteDecisionStore,
    SQLiteWorkflowStore,
    WorkflowRunResult,
    WorkflowTimeline,
)
from .controller.workflow_timeline import (
    SQLiteWorkflowFeedbackStore,
    WorkflowFeedback,
    WorkflowFeedbackAction,
)
from .controller.policy.route_decision import RouteDecision
from .controller.policy.route_store import SQLiteRouteDecisionStore
from .core.state import ResearchState
from .documents import (
    DocumentCreateRequest,
    DocumentError,
    DocumentFormat,
    DocumentPatchRequest,
    DocumentService,
    DocumentVersion,
    DocumentVersionCreateRequest,
    ProjectDocument,
)
from .knowledge import (
    ConversationSummary,
    CorpusManifest,
    HybridContextBuildRequest,
    HybridKnowledgeService,
    MemoryTurn,
    QAAnswerRequest,
    QAAnswerResponse,
    QuestionAnswerService,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    SharedCorpusSummary,
)
from .knowledge.manifest import CorpusRegistry
from .operators.executor import OperatorExecutor
from .operators.knowledge import KnowledgeOperatorRuntime
from .operators.models import OperatorRun, OperatorSpec
from .operators.registry import OperatorRegistry
from .provenance.agent_run_store import SQLiteAgentRunStore
from .provenance.models import AgentRunRecord
from .settings import ConfigurationReport, validate_environment

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
logger = logging.getLogger("stem_sci.api")
configuration_report: ConfigurationReport

# Load repository-local switches before constructing Controller services.
_repository_root = Path(__file__).resolve().parents[3]
for _dotenv_path in (_repository_root / ".env", _repository_root / ".env.local"):
    load_dotenv(_dotenv_path, override=False)


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


class UTF8JSONResponse(JSONResponse):
    """JSON response with an explicit charset for legacy HTTP clients."""

    media_type = "application/json; charset=utf-8"


def _error(status_code: int, code: str, message: str) -> UTF8JSONResponse:
    return UTF8JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
    )


app = FastAPI(
    title="STEM-SCI Research Workflow Platform",
    version="0.2.0",
    default_response_class=UTF8JSONResponse,
)
configuration_report = validate_environment()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
storage_root = Path(os.getenv("STEM_SCI_STORAGE_DIR", ".stem_sci"))
service = ContextService(storage_root, max_upload_bytes=_max_upload_bytes())
knowledge_service = HybridKnowledgeService(service, CorpusRegistry())
workflow_database = storage_root / "workflow.db"
identity_service = IdentityService(storage_root / "identity.db")
document_service = DocumentService(storage_root / "documents.db", storage_root / "project-documents")


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
route_store = SQLiteRouteDecisionStore(workflow_database)
knowledge_operator_runtime = KnowledgeOperatorRuntime(
    knowledge_service,
    artifact_store=artifact_store,
    artifact_content_store=artifact_content_store,
)
workflow_operator_executor = OperatorExecutor(
    registry=operator_registry,
    execution_store=execution_store,
    handlers=knowledge_operator_runtime.handlers(),
)


def _configured_qa_service() -> QuestionAnswerService:
    """Create the chat service; provider configuration remains environment-only."""

    api_key = os.getenv("STEM_SCI_LLM_API_KEY", "").strip()
    provider = None
    if api_key:
        try:
            provider = GPTProvider.from_env()
        except ValueError:
            # The QA endpoint remains available in deterministic fallback mode
            # while the provider environment is incomplete.
            provider = None
    return QuestionAnswerService(
        knowledge_service=knowledge_service,
        storage_root=storage_root,
        provider=provider,
        workflow_controller=workflow_controller,
        artifact_store=artifact_store,
    )


def _configured_context_provider() -> LocalContextProvider | HybridContextProvider:
    configured = os.getenv("STEM_SCI_CONTEXT_PROVIDER", "local").strip().lower()
    if configured == "local":
        return LocalContextProvider(service)
    if configured == "hybrid":
        return HybridContextProvider(knowledge_service)
    raise ValueError("STEM_SCI_CONTEXT_PROVIDER must be local or hybrid")


workflow_controller = ResearchController(
    dispatcher=AgentDispatcher(_configured_agent_registry()),
    context_provider=_configured_context_provider(),
    decision_store=SQLiteDecisionStore(workflow_database),
    workflow_store=SQLiteWorkflowStore(workflow_database),
    operator_executor=workflow_operator_executor,
    artifact_store=artifact_store,
    artifact_content_store=artifact_content_store,
    agent_run_store=agent_run_store,
    route_store=route_store,
    feedback_store=SQLiteWorkflowFeedbackStore(workflow_database),
    data_pipeline_root=storage_root,
)
qa_service = _configured_qa_service()


class WorkflowProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    research_intent: str = Field(min_length=1)
    context_bundle_ref: str = "context://initial"
    run_id: str | None = None


class ProjectWorkflowStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    research_intent: str = Field(min_length=1)
    context_bundle_ref: str = "context://initial"
    run_id: str | None = None


class WorkflowApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)


class ProjectWorkflowFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    stage: str = Field(min_length=1, max_length=64)
    action: WorkflowFeedbackAction
    feedback: str = Field(min_length=1, max_length=10_000)


def _access_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if authorization is None:
        raise AuthError(401, "missing_access_token", "Authorization bearer token is required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError(401, "invalid_authorization_header", "Authorization must use Bearer token")
    return token.strip()


def current_user(token: Annotated[str, Depends(_access_token)]) -> UserProfile:
    return identity_service.user_for_access_token(token)


@app.exception_handler(ContextInputError)
async def handle_context_input(_: Request, error: ContextInputError) -> JSONResponse:
    return _error(400, error.code, str(error))


@app.exception_handler(ContextNotFoundError)
async def handle_not_found(_: Request, error: ContextNotFoundError) -> JSONResponse:
    return _error(404, "not_found", f"{error.resource} was not found")


@app.exception_handler(AuthError)
async def handle_auth_error(_: Request, error: AuthError) -> JSONResponse:
    return _error(error.status_code, error.code, error.message)


@app.exception_handler(DocumentError)
async def handle_document_error(_: Request, error: DocumentError) -> JSONResponse:
    return _error(error.status_code, error.code, error.message)


@app.exception_handler(ValueError)
async def handle_workflow_value_error(_: Request, error: ValueError) -> JSONResponse:
    return _error(400, "workflow_input_error", str(error))


@app.exception_handler(RequestValidationError)
async def handle_validation(_: Request, __: RequestValidationError) -> JSONResponse:
    return _error(422, "invalid_request", "Request does not match the API contract")


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, error: StarletteHTTPException) -> JSONResponse:
    return _error(error.status_code, "http_error", "Request could not be completed")


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, error: Exception) -> JSONResponse:
    # Keep provider/database details out of the HTTP response, but retain the
    # traceback in the backend console for local debugging.
    logger.exception("Unhandled API exception: %s", error)
    return _error(500, "internal_error", "An internal error occurred")


ProjectIdForm = Annotated[
    str,
    Form(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]
ProjectIdQuery = Annotated[
    str,
    Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


async def _read_uploaded_research_document(
    file: UploadFile, max_bytes: int
) -> tuple[DocumentFormat, str]:
    """Extract searchable text from a PDF or DOCX upload."""
    filename = (file.filename or "").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise DocumentError(
            415,
            "unsupported_document_format",
            "Only PDF and DOCX files are supported",
        )

    payload = await file.read()
    if not payload:
        raise DocumentError(400, "empty_document", "The uploaded document is empty")
    if len(payload) > max_bytes:
        raise DocumentError(413, "document_too_large", "The uploaded document exceeds the upload limit")

    document_format: DocumentFormat
    try:
        if suffix == ".pdf":
            reader = PdfReader(io.BytesIO(payload))
            content = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
            document_format = "pdf"
        else:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                xml_payload = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_payload)
            paragraphs: list[str] = []
            for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                text = "".join(
                    node.text or ""
                    for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
                ).strip()
                if text:
                    paragraphs.append(text)
            content = "\n\n".join(paragraphs).strip()
            document_format = "docx"
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise DocumentError(
            400,
            "document_parse_failed",
            "The uploaded document could not be parsed",
        ) from exc

    if not content:
        raise DocumentError(
            422,
            "document_text_unavailable",
            "The uploaded document does not contain extractable text",
        )
    if len(content) > 1_000_000:
        raise DocumentError(
            413,
            "document_text_too_large",
            "The extracted document text exceeds the storage limit",
        )
    return document_format, content


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "stem-sci-backend",
        "configuration_valid": configuration_report.valid,
        "warnings": list(configuration_report.warnings),
    }


@app.post("/api/v1/auth/register", response_model=AuthTokenPair)
def auth_register(request: UserCreateRequest) -> AuthTokenPair:
    """Create a user and return an immediately usable session."""
    return identity_service.register(request)


@app.post("/api/v1/auth/login", response_model=AuthTokenPair)
def auth_login(request: LoginRequest) -> AuthTokenPair:
    return identity_service.login(request)


@app.post("/api/v1/auth/refresh", response_model=AuthTokenPair)
def auth_refresh(request: TokenRefreshRequest) -> AuthTokenPair:
    return identity_service.refresh(request)


@app.post("/api/v1/auth/logout")
def auth_logout(token: Annotated[str, Depends(_access_token)]) -> dict[str, str]:
    identity_service.logout(token)
    return {"status": "ok"}


@app.get("/api/v1/auth/me", response_model=UserProfile)
def auth_me(user: Annotated[UserProfile, Depends(current_user)]) -> UserProfile:
    return user


@app.get("/api/v1/projects", response_model=list[ResearchProject])
def projects(user: Annotated[UserProfile, Depends(current_user)]) -> list[ResearchProject]:
    return identity_service.list_projects(user)


@app.post("/api/v1/projects", response_model=ResearchProject)
def create_project(
    request: ProjectCreateRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ResearchProject:
    return identity_service.create_project(user, request)


@app.get("/api/v1/projects/{project_id}", response_model=ResearchProject)
def project(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ResearchProject:
    return identity_service.get_project(user, project_id)


@app.patch("/api/v1/projects/{project_id}", response_model=ResearchProject)
def patch_project(
    project_id: str,
    request: ProjectPatchRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ResearchProject:
    return identity_service.patch_project(user, project_id, request)


@app.delete("/api/v1/projects/{project_id}")
def delete_project(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> dict[str, str]:
    identity_service.delete_project(user, project_id)
    return {"status": "deleted"}


@app.get("/api/v1/projects/{project_id}/documents", response_model=list[ProjectDocument])
def project_documents(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> list[ProjectDocument]:
    identity_service.get_project(user, project_id)
    return document_service.list_project(project_id)


@app.post("/api/v1/projects/{project_id}/documents", response_model=ProjectDocument)
def create_project_document(
    project_id: str,
    request: DocumentCreateRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ProjectDocument:
    identity_service.get_project(user, project_id)
    return document_service.create(project_id=project_id, user=user, request=request)


@app.post("/api/v1/projects/{project_id}/documents/upload", response_model=ProjectDocument)
async def upload_project_document(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str | None, Form()] = None,
) -> ProjectDocument:
    identity_service.get_project(user, project_id)
    document_format, content = await _read_uploaded_research_document(file, _max_upload_bytes())
    document_title = (title or Path(file.filename or "uploaded-document").stem).strip()
    if not document_title:
        raise DocumentError(422, "document_title_required", "A document title is required")
    return document_service.create(
        project_id=project_id,
        user=user,
        request=DocumentCreateRequest(
            title=document_title,
            document_type="reference",
            format=document_format,
            content=content,
            change_note=f"Uploaded from {file.filename or 'file'}",
        ),
    )


@app.get("/api/v1/projects/{project_id}/documents/{document_id}", response_model=ProjectDocument)
def project_document(
    project_id: str,
    document_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ProjectDocument:
    identity_service.get_project(user, project_id)
    return document_service.get(project_id, document_id)


@app.patch("/api/v1/projects/{project_id}/documents/{document_id}", response_model=ProjectDocument)
def patch_project_document(
    project_id: str,
    document_id: str,
    request: DocumentPatchRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ProjectDocument:
    identity_service.get_project(user, project_id)
    return document_service.patch(
        project_id=project_id,
        document_id=document_id,
        user=user,
        request=request,
    )


@app.delete("/api/v1/projects/{project_id}/documents/{document_id}")
def delete_project_document(
    project_id: str,
    document_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> dict[str, str]:
    identity_service.get_project(user, project_id)
    document_service.delete(project_id=project_id, document_id=document_id, user=user)
    return {"status": "deleted"}


@app.get(
    "/api/v1/projects/{project_id}/documents/{document_id}/versions",
    response_model=list[DocumentVersion],
)
def project_document_versions(
    project_id: str,
    document_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> list[DocumentVersion]:
    identity_service.get_project(user, project_id)
    return document_service.list_versions(project_id, document_id)


@app.post(
    "/api/v1/projects/{project_id}/documents/{document_id}/versions",
    response_model=DocumentVersion,
)
def create_project_document_version(
    project_id: str,
    document_id: str,
    request: DocumentVersionCreateRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> DocumentVersion:
    identity_service.get_project(user, project_id)
    return document_service.create_version(
        project_id=project_id,
        document_id=document_id,
        user=user,
        request=request,
    )


@app.get(
    "/api/v1/projects/{project_id}/documents/{document_id}/versions/{version}",
    response_model=DocumentVersion,
)
def project_document_version(
    project_id: str,
    document_id: str,
    version: int,
    user: Annotated[UserProfile, Depends(current_user)],
) -> DocumentVersion:
    identity_service.get_project(user, project_id)
    return document_service.get_version(project_id, document_id, version)


@app.get("/api/v1/corpora", response_model=list[SharedCorpusSummary])
def corpora() -> list[SharedCorpusSummary]:
    """List shared corpora and their safe readiness summaries."""
    result: list[SharedCorpusSummary] = []
    for manifest in knowledge_service.list_corpora():
        readiness = knowledge_service.readiness(manifest.corpus_id)
        result.append(
            SharedCorpusSummary(
                corpus_id=manifest.corpus_id,
                corpus_version=manifest.corpus_version,
                access_mode=manifest.access_mode,
                paper_count=manifest.paper_count,
                vector_chunk_count=manifest.vector_chunk_count,
                discovery_ready=readiness.discovery_ready,
                formal_evidence_ready=readiness.formal_evidence_ready,
                risk_flags=readiness.risk_flags,
            )
        )
    return result


@app.get("/api/v1/corpora/{corpus_id}/manifest", response_model=CorpusManifest)
def corpus_manifest(corpus_id: str) -> CorpusManifest:
    """Return a manifest without turning local absolute file paths into API output."""
    manifest = knowledge_service.manifest(corpus_id)
    return manifest


@app.post("/api/v1/retrieval/search", response_model=RetrievalSearchResponse)
def hybrid_search(request: RetrievalSearchRequest) -> RetrievalSearchResponse:
    """Search the read-only corpus; graph triples remain navigation-only."""
    return knowledge_service.search(request)


@app.post("/api/v1/context/hybrid-build")
def hybrid_build_context(request: HybridContextBuildRequest) -> ContextBundle:
    """Build a discovery or fail-closed formal shared-corpus ContextBundle."""
    return knowledge_service.build_from_request(request)


@app.post("/api/v1/qa/answer", response_model=QAAnswerResponse)
def qa_answer(request: QAAnswerRequest) -> QAAnswerResponse:
    """Run rewrite, hybrid retrieval, answer synthesis, and memory persistence."""

    return qa_service.answer(request)


@app.post("/api/v1/projects/{project_id}/chat/answer", response_model=QAAnswerResponse)
def project_chat_answer(
    project_id: str,
    request: QAAnswerRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> QAAnswerResponse:
    """Project-scoped conversational QA with membership enforced."""

    if request.project_id != project_id:
        raise ContextInputError("project_mismatch", "path project_id does not match request project_id")
    identity_service.get_project(user, project_id)
    return qa_service.answer(request)


@app.get("/api/v1/projects/{project_id}/conversations", response_model=list[ConversationSummary])
def project_conversations(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ConversationSummary]:
    """List persisted QA conversations for a project the user can access."""

    identity_service.get_project(user, project_id)
    return qa_service.list_conversations(project_id, limit=limit)


@app.get(
    "/api/v1/projects/{project_id}/conversations/{conversation_id}/turns",
    response_model=list[MemoryTurn],
)
def project_conversation_turns(
    project_id: str,
    conversation_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemoryTurn]:
    """Return ordered QA turns for one project-scoped conversation."""

    identity_service.get_project(user, project_id)
    return qa_service.conversation_turns(project_id, conversation_id, limit=limit)


@app.post("/api/v1/projects/{project_id}/workflow")
def start_project_workflow(
    project_id: str,
    request: ProjectWorkflowStartRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> PlanningRunResult:
    """Start workflow planning inside an authenticated research project."""

    identity_service.get_project(user, project_id)
    return workflow_controller.start_planning(
        PlanningRequest(
            project_id=project_id,
            research_intent=request.research_intent,
            context_bundle_ref=request.context_bundle_ref,
            run_id=request.run_id or f"planning-{project_id}",
        )
    )


@app.get("/api/v1/projects/{project_id}/workflow")
def project_workflow(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ControllerWorkflowState:
    identity_service.get_project(user, project_id)
    return workflow_controller.get_state(project_id)


@app.get("/api/v1/projects/{project_id}/workflow/timeline", response_model=WorkflowTimeline)
def project_workflow_timeline(project_id: str, user: Annotated[UserProfile, Depends(current_user)]) -> WorkflowTimeline:
    identity_service.get_project(user, project_id)
    return workflow_controller.workflow_timeline(project_id)


@app.post("/api/v1/projects/{project_id}/workflow/feedback", response_model=WorkflowFeedbackResult)
def project_workflow_feedback(
    project_id: str,
    request: ProjectWorkflowFeedbackRequest,
    user: Annotated[UserProfile, Depends(current_user)],
) -> WorkflowFeedbackResult:
    identity_service.get_project(user, project_id)
    return workflow_controller.apply_workflow_feedback(WorkflowFeedback(
        feedback_id=f"feedback-{uuid4().hex}", project_id=project_id,
        agent_id=request.agent_id, stage=request.stage, action=request.action,
        feedback=request.feedback, created_by=user.username,
    ))


@app.post("/api/v1/projects/{project_id}/workflow/next")
def project_workflow_next(
    project_id: str,
    user: Annotated[UserProfile, Depends(current_user)],
) -> WorkflowRunResult:
    identity_service.get_project(user, project_id)
    return workflow_controller.run_next(project_id)


@app.post("/api/v1/projects/{project_id}/workflow/approve")
def project_workflow_approve(
    project_id: str,
    request: WorkflowApprovalInput,
    user: Annotated[UserProfile, Depends(current_user)],
) -> ResearchState:
    identity_service.get_project(user, project_id)
    approval = workflow_controller.get_pending_approval(project_id)
    return workflow_controller.resume_approval(
        project_id,
        approval,
        decision=request.decision,
        decided_by=request.decided_by,
    )


@app.post("/api/v1/projects/{project_id}/workflow/data-pipeline/raw")
async def project_register_data_pipeline_raw_csv(
    project_id: str,
    file: Annotated[UploadFile, File(...)],
    user: Annotated[UserProfile, Depends(current_user)],
) -> DataPipelineState:
    """Authenticated project-scoped CSV upload for the approved data gate."""

    identity_service.get_project(user, project_id)
    return workflow_controller.register_data_pipeline_raw_csv(
        project_id,
        filename=file.filename or "upload.csv",
        content=await file.read(),
    )


@app.post("/api/v1/projects/{project_id}/workflow/data-pipeline/decide")
def project_decide_data_pipeline(
    project_id: str,
    request: WorkflowApprovalInput,
    user: Annotated[UserProfile, Depends(current_user)],
) -> DataPipelineState:
    """Authenticated human decision for processing, freeze, or execution."""

    identity_service.get_project(user, project_id)
    return workflow_controller.decide_data_pipeline(
        project_id,
        decision=request.decision,
        decided_by=request.decided_by,
    )


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


@app.get("/api/v1/workflow/runtime")
def workflow_runtime() -> dict[str, object]:
    """Expose safe local capability status without returning executable paths."""
    pipeline = workflow_controller.data_pipeline
    provider = pipeline.research_execution.coding_provider
    health_reason = getattr(provider, "health_reason", None)
    codex_reason = health_reason() if callable(health_reason) else None
    spss = pipeline.dual_engine_execution.spss_adapter.detect()
    provider_name = os.getenv("STEM_SCI_CODING_PROVIDER", "deterministic").strip().lower()
    codex_available = provider_name == "codex" and codex_reason is None
    return {
        "coding_provider": provider_name,
        "codex_available": codex_available,
        "codex_reason": (codex_reason if provider_name == "codex" else "CODEX_PROVIDER_NOT_SELECTED"),
        "spss_available": spss.available,
        "spss_reason": spss.reason_code,
    }


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


@app.get("/api/v1/workflow/projects/{project_id}/routes")
def workflow_routes(project_id: str) -> list[RouteDecision]:
    return route_store.list_project(project_id)


@app.post("/api/v1/workflow/projects/{project_id}/review-findings")
def workflow_review_finding(project_id: str, finding: ReviewFinding) -> ResearchState:
    return workflow_controller.route_review_finding(project_id, finding)


@app.post("/api/v1/workflow/projects/{project_id}/reviews/reproducibility")
def workflow_reproducibility_review(
    project_id: str, request: ReproducibilityReviewRequest
) -> ReproducibilityReviewRunResult:
    if request.project_id != project_id:
        raise ContextInputError("project_mismatch", "path project_id does not match request project_id")
    return workflow_controller.run_reproducibility_review(request)


@app.post("/api/v1/workflow/projects/{project_id}/data-pipeline/start")
def start_data_pipeline(
    project_id: str, request: DataPipelineBeginRequest
) -> DataPipelineState:
    if request.project_id != project_id:
        raise ContextInputError("project_mismatch", "path project_id does not match request project_id")
    return workflow_controller.begin_data_pipeline(request)


@app.post("/api/v1/workflow/projects/{project_id}/data-pipeline/raw")
async def register_data_pipeline_raw_csv(
    project_id: str,
    file: Annotated[UploadFile, File(...)],
) -> DataPipelineState:
    return workflow_controller.register_data_pipeline_raw_csv(
        project_id,
        filename=file.filename or "upload.csv",
        content=await file.read(),
    )


@app.post("/api/v1/workflow/projects/{project_id}/data-pipeline/decide")
def decide_data_pipeline(
    project_id: str, request: WorkflowApprovalInput
) -> DataPipelineState:
    return workflow_controller.decide_data_pipeline(
        project_id,
        decision=request.decision,
        decided_by=request.decided_by,
    )


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
