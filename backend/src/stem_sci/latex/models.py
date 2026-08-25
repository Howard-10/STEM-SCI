"""API contracts for deterministic LaTeX manuscript generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LatexModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LatexTemplate(LatexModel):
    template_id: str
    name: str
    venue_type: Literal["journal", "conference", "generic"]
    publisher: str
    description: str
    version: str
    source_url: str | None = None
    official_status: Literal["official", "community", "generic"]
    document_class: str
    supports_bibliography: bool = True


class LatexCompileResult(LatexModel):
    status: Literal["compiled", "skipped", "failed"]
    engine: str | None = None
    pdf_available: bool = False
    log: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LatexGenerateRequest(LatexModel):
    template_id: str = Field(min_length=1, max_length=100)
    title: str = Field(default="Untitled manuscript", min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=50)
    abstract: str = Field(default="", max_length=100_000)
    content: str = Field(default="", max_length=1_000_000)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    bibliography: str = Field(default="", max_length=500_000)
    compile_pdf: bool = False


class LatexGenerateResponse(LatexModel):
    template: LatexTemplate
    latex: str
    sha256: str
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    compile: LatexCompileResult
