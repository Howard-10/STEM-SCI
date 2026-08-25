"""Contracts for project-scoped manuscript and reference documents."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["manuscript", "reference", "dataset", "protocol", "note"]
DocumentFormat = Literal["markdown", "text", "pdf", "docx", "csv"]
DocumentStatus = Literal["active", "archived"]


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentCreateRequest(DocumentModel):
    title: str = Field(min_length=1, max_length=180)
    document_type: DocumentType = "manuscript"
    format: DocumentFormat = "markdown"
    content: str = Field(default="", max_length=1_000_000)
    change_note: str | None = Field(default=None, max_length=500)


class DocumentPatchRequest(DocumentModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    document_type: DocumentType | None = None
    status: DocumentStatus | None = None


class DocumentVersionCreateRequest(DocumentModel):
    content: str = Field(max_length=1_000_000)
    change_note: str | None = Field(default=None, max_length=500)


class ProjectDocument(DocumentModel):
    document_id: str
    project_id: str
    title: str
    document_type: DocumentType
    format: DocumentFormat
    status: DocumentStatus = "active"
    current_version: int
    current_sha256: str
    size_bytes: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class DocumentVersion(DocumentModel):
    document_id: str
    project_id: str
    version: int
    format: DocumentFormat
    content: str
    sha256: str
    size_bytes: int
    storage_ref: str
    change_note: str | None = None
    created_by: str
    created_at: datetime
