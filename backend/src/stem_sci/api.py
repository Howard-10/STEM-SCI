"""FastAPI surface for the project-scoped Context MVP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
from .context.service import ContextInputError, ContextNotFoundError, ContextService

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    configured = os.getenv("STEM_SCI_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
    )


app = FastAPI(title="STEM-SCI Context MVP", version="0.1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
service = ContextService(Path(os.getenv("STEM_SCI_STORAGE_DIR", ".stem_sci")))


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
