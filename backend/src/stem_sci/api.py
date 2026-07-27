"""FastAPI surface for the context MVP."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile

from .context.models import (
    ContextBuildRequest,
    ContextBundle,
    EvidenceDetail,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    SourceChunk,
    SourceDocument,
)
from .context.service import ContextService

app = FastAPI(title="STEM-SCI Context MVP", version="0.1.0")
service = ContextService(Path(os.getenv("STEM_SCI_STORAGE_DIR", ".stem_sci")))

@app.get("/api/v1/health")
def health() -> dict[str, str]: return {"status": "ok"}

@app.post("/api/v1/sources/import")
async def import_source(file: Annotated[UploadFile, File(...)]) -> SourceDocument:
    try: return service.import_bytes(file.filename or "upload.txt", await file.read())
    except ValueError as error: raise HTTPException(400, str(error)) from error

@app.get("/api/v1/sources")
def sources() -> list[SourceDocument]: return service.list_sources()

@app.get("/api/v1/sources/{source_id}")
def source(source_id: str) -> SourceDocument:
    try: return service.get_source(source_id)
    except KeyError as error: raise HTTPException(404, "source not found") from error

@app.get("/api/v1/sources/{source_id}/chunks")
def chunks(source_id: str) -> list[SourceChunk]:
    try: return service.chunks(source_id)
    except KeyError as error: raise HTTPException(404, "source not found") from error

@app.post("/api/v1/evidence/search")
def search(request: EvidenceSearchRequest) -> list[EvidenceSearchResult]: return service.search(request)

@app.get("/api/v1/evidence/{evidence_id}")
def evidence(evidence_id: str) -> EvidenceDetail:
    try: return service.get_evidence(evidence_id)
    except KeyError as error: raise HTTPException(404, "evidence not found") from error

@app.post("/api/v1/evidence/{evidence_id}/verify-source")
def verify(evidence_id: str, verified_by: str, verification_note: str) -> EvidenceRef:
    try: return service.verify_source(evidence_id, verified_by, verification_note)
    except (KeyError, ValueError) as error: raise HTTPException(400, str(error)) from error

@app.post("/api/v1/context/build")
def build(request: ContextBuildRequest) -> ContextBundle: return service.build(request)

@app.get("/api/v1/context/{context_id}")
def context(context_id: str) -> ContextBundle:
    try: return service.get_bundle(context_id)
    except KeyError as error: raise HTTPException(404, "context not found") from error
