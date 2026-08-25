"""Validated chunk-to-PDF locators for formal shared-corpus evidence."""

from __future__ import annotations

import hashlib
import unicodedata
from bisect import bisect_right
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from stem_sci.context.models import VerificationStatus

from .identity import PaperIdentityResolver
from .models import StrictKnowledgeModel
from .retrievers import ChunkRecord, LocalMetadataCorpus

LocatorMethod = Literal["PAGE_TEXT_EXACT", "NORMALIZED_TEXT_MATCH", "UNRESOLVED"]


class ChunkLocator(StrictKnowledgeModel):
    """One reproducible mapping from a vector chunk to an original PDF."""

    canonical_chunk_id: str
    canonical_paper_id: str
    source_filename: str
    pdf_relative_path: str
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chunk_index: int = Field(ge=0)
    quote_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    source_locator_method: LocatorMethod
    verification_status: VerificationStatus
    verification_note: str | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> ChunkLocator:
        positions = (self.page_start, self.page_end, self.char_start, self.char_end)
        if self.source_locator_method == "UNRESOLVED":
            if any(value is not None for value in positions):
                raise ValueError("unresolved locators cannot declare source positions")
            if self.verification_status in {
                VerificationStatus.SOURCE_VERIFIED,
                VerificationStatus.HUMAN_VERIFIED,
            }:
                raise ValueError("unresolved locators cannot be verified")
            return self
        if any(value is None for value in positions):
            raise ValueError("resolved locators require page and character positions")
        assert self.page_start is not None and self.page_end is not None
        assert self.char_start is not None and self.char_end is not None
        if self.page_end < self.page_start or self.char_end <= self.char_start:
            raise ValueError("locator ranges are invalid")
        return self

    @property
    def eligible_for_formal_use(self) -> bool:
        return self.source_locator_method != "UNRESOLVED" and self.verification_status in {
            VerificationStatus.SOURCE_VERIFIED,
            VerificationStatus.HUMAN_VERIFIED,
        }


class LocatorIndex(StrictKnowledgeModel):
    """Versioned locator artifact containing no PDF or full-text content."""

    artifact_type: Literal["PhysicsStemChunkLocatorIndex"]
    artifact_version: str
    corpus_id: str
    corpus_version: str
    generated_at: str
    paper_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    source_verified_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    records: list[ChunkLocator]

    @model_validator(mode="after")
    def validate_counts(self) -> LocatorIndex:
        ids = [record.canonical_chunk_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("locator index contains duplicate canonical chunk IDs")
        resolved = sum(record.source_locator_method != "UNRESOLVED" for record in self.records)
        verified = sum(record.eligible_for_formal_use for record in self.records)
        if self.chunk_count != len(self.records):
            raise ValueError("locator chunk_count does not match records")
        if self.resolved_count != resolved or self.unresolved_count != len(self.records) - resolved:
            raise ValueError("locator resolution counts do not match records")
        if self.source_verified_count != verified:
            raise ValueError("locator verification count does not match records")
        return self

    @classmethod
    def from_path(cls, path: Path) -> LocatorIndex:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def by_chunk_id(self) -> dict[str, ChunkLocator]:
        return {record.canonical_chunk_id: record for record in self.records}


class PdfAudit(StrictKnowledgeModel):
    expected_papers: int
    discovered_pdfs: int
    matched_papers: int
    missing_filenames: list[str]
    duplicate_filenames: dict[str, list[str]]
    extra_filenames: list[str]
    unreadable_filenames: list[str]
    empty_text_filenames: list[str]
    duplicate_sha256_groups: list[list[str]]

    @property
    def ready(self) -> bool:
        return not (
            self.missing_filenames
            or self.duplicate_filenames
            or self.extra_filenames
            or self.unreadable_filenames
            or self.empty_text_filenames
            or self.duplicate_sha256_groups
        )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalise_with_offsets(text: str, *, aggressive: bool) -> tuple[str, list[int]]:
    output: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for position, source_char in enumerate(text):
        expanded = unicodedata.normalize("NFKC", source_char)
        for char in expanded:
            if aggressive:
                folded = char.casefold()
                for folded_char in folded:
                    if folded_char.isalnum():
                        output.append(folded_char)
                        offsets.append(position)
                continue
            if char.isspace():
                pending_space = bool(output)
                continue
            if pending_space:
                output.append(" ")
                offsets.append(position)
                pending_space = False
            output.append(char)
            offsets.append(position)
    return "".join(output), offsets


def _unique_match(document: str, quote: str, offsets: list[int]) -> tuple[int, int] | None:
    if not quote:
        return None
    start = document.find(quote)
    if start < 0 or document.find(quote, start + 1) >= 0:
        return None
    end = start + len(quote)
    return offsets[start], offsets[end - 1] + 1


def _page_for_offset(page_starts: list[int], offset: int) -> int:
    return max(1, bisect_right(page_starts, offset))


def _pdf_inventory(
    pdf_root: Path, expected_filenames: set[str]
) -> tuple[PdfAudit, dict[str, Path]]:
    import pdfplumber

    files = sorted(pdf_root.rglob("*.pdf"))
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        by_name[path.name.casefold()].append(path)
    missing = sorted(expected_filenames - set(by_name))
    extras = sorted(set(by_name) - expected_filenames)
    duplicates = {
        name: [str(path.relative_to(pdf_root)).replace("\\", "/") for path in paths]
        for name, paths in by_name.items()
        if name in expected_filenames and len(paths) != 1
    }
    unreadable: list[str] = []
    empty: list[str] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    selected: dict[str, Path] = {}
    for name in sorted(expected_filenames & set(by_name)):
        paths = by_name[name]
        if len(paths) != 1:
            continue
        path = paths[0]
        relative = str(path.relative_to(pdf_root)).replace("\\", "/")
        try:
            raw = path.read_bytes()
            with pdfplumber.open(path) as pdf_document:
                extracted = "".join(page.extract_text() or "" for page in pdf_document.pages)
        except Exception:  # noqa: BLE001 - the audit must report every parser failure
            unreadable.append(relative)
            continue
        hashes[_sha256_bytes(raw)].append(relative)
        if not extracted.strip():
            empty.append(relative)
            continue
        selected[name] = path
    duplicate_hashes = [paths for paths in hashes.values() if len(paths) > 1]
    audit = PdfAudit(
        expected_papers=len(expected_filenames),
        discovered_pdfs=len(files),
        matched_papers=len(selected),
        missing_filenames=missing,
        duplicate_filenames=duplicates,
        extra_filenames=[by_name[name][0].name for name in extras],
        unreadable_filenames=unreadable,
        empty_text_filenames=empty,
        duplicate_sha256_groups=duplicate_hashes,
    )
    return audit, selected


def build_locator_index(
    *,
    corpus_id: str,
    corpus_version: str,
    pdf_root: Path,
    identity_map_path: Path,
    metadata_path: Path,
) -> tuple[PdfAudit, LocatorIndex]:
    """Audit PDFs and create conservative, reproducible chunk locators."""

    import pdfplumber

    resolver = PaperIdentityResolver.from_catalog_path(identity_map_path)
    corpus = LocalMetadataCorpus.from_metadata_path(metadata_path, resolver)
    expected = {record.source_filename.casefold() for record in corpus.records}
    audit, pdf_paths = _pdf_inventory(pdf_root, expected)
    if not audit.ready:
        raise ValueError(f"PDF corpus audit failed: {audit.model_dump_json()}")

    records_by_paper: dict[str, list[ChunkRecord]] = defaultdict(list)
    for record in corpus.records:
        records_by_paper[record.canonical_paper_id].append(record)
    locator_records: list[ChunkLocator] = []
    for paper_records in records_by_paper.values():
        paper_records.sort(key=lambda item: (item.chunk_index, item.canonical_chunk_id))
        pdf_path = pdf_paths[paper_records[0].source_filename.casefold()]
        raw = pdf_path.read_bytes()
        with pdfplumber.open(pdf_path) as pdf_document:
            pages = [page.extract_text() or "" for page in pdf_document.pages]
        page_starts: list[int] = []
        document_parts: list[str] = []
        cursor = 0
        for page in pages:
            page_starts.append(cursor)
            document_parts.append(page)
            cursor += len(page) + 1
        document_text = "\n".join(document_parts)
        exact_document, exact_offsets = _normalise_with_offsets(document_text, aggressive=False)
        broad_document, broad_offsets = _normalise_with_offsets(document_text, aggressive=True)
        pdf_sha256 = _sha256_bytes(raw)
        relative_path = str(pdf_path.relative_to(pdf_root)).replace("\\", "/")
        for chunk in paper_records:
            exact_quote, _ = _normalise_with_offsets(chunk.text, aggressive=False)
            match = _unique_match(exact_document, exact_quote, exact_offsets)
            method: LocatorMethod = "PAGE_TEXT_EXACT"
            verification = VerificationStatus.SOURCE_VERIFIED
            note = "Unique whitespace-normalized match in extracted PDF page text"
            if match is None:
                broad_quote, _ = _normalise_with_offsets(chunk.text, aggressive=True)
                match = _unique_match(broad_document, broad_quote, broad_offsets)
                method = "NORMALIZED_TEXT_MATCH"
                verification = VerificationStatus.MODEL_GENERATED_UNVERIFIED
                note = "Unique aggressive normalized match; human verification required"
            if match is None:
                locator_records.append(
                    ChunkLocator(
                        canonical_chunk_id=chunk.canonical_chunk_id,
                        canonical_paper_id=chunk.canonical_paper_id,
                        source_filename=chunk.source_filename,
                        pdf_relative_path=relative_path,
                        pdf_sha256=pdf_sha256,
                        chunk_index=chunk.chunk_index,
                        quote_sha256=_sha256_bytes(chunk.text.encode("utf-8")),
                        source_locator_method="UNRESOLVED",
                        verification_status=VerificationStatus.MODEL_GENERATED_UNVERIFIED,
                        verification_note="No unique match in extracted PDF text",
                    )
                )
                continue
            char_start, char_end = match
            locator_records.append(
                ChunkLocator(
                    canonical_chunk_id=chunk.canonical_chunk_id,
                    canonical_paper_id=chunk.canonical_paper_id,
                    source_filename=chunk.source_filename,
                    pdf_relative_path=relative_path,
                    pdf_sha256=pdf_sha256,
                    chunk_index=chunk.chunk_index,
                    quote_sha256=_sha256_bytes(chunk.text.encode("utf-8")),
                    page_start=_page_for_offset(page_starts, char_start),
                    page_end=_page_for_offset(page_starts, max(char_start, char_end - 1)),
                    char_start=char_start,
                    char_end=char_end,
                    source_locator_method=method,
                    verification_status=verification,
                    verification_note=note,
                )
            )
    locator_records.sort(key=lambda item: item.canonical_chunk_id)
    resolved = sum(item.source_locator_method != "UNRESOLVED" for item in locator_records)
    verified = sum(item.eligible_for_formal_use for item in locator_records)
    return audit, LocatorIndex(
        artifact_type="PhysicsStemChunkLocatorIndex",
        artifact_version="1.0.0",
        corpus_id=corpus_id,
        corpus_version=corpus_version,
        generated_at=datetime.now(UTC).isoformat(),
        paper_count=len(records_by_paper),
        chunk_count=len(locator_records),
        resolved_count=resolved,
        source_verified_count=verified,
        unresolved_count=len(locator_records) - resolved,
        records=locator_records,
    )


def write_locator_index(index: LocatorIndex, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = index.model_dump_json(indent=2) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    return _sha256_bytes(output_path.read_bytes())
