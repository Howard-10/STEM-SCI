"""Local deterministic ingestion, search, verification, and context assembly."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from pypdf import PdfReader

from .models import (
    ContextBuildRequest,
    ContextBundle,
    EvidenceDetail,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    SourceChunk,
    SourceDocument,
    SourceLocation,
    VerificationStatus,
)

DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEMO_MARKER = "STEM_SCI_DEMO_SEED: true"
STATUS_ORDER = {
    VerificationStatus.HUMAN_VERIFIED.value: 0,
    VerificationStatus.SOURCE_VERIFIED.value: 1,
    VerificationStatus.DEMO_SEED.value: 2,
    VerificationStatus.MODEL_GENERATED_UNVERIFIED.value: 3,
}


class ContextInputError(ValueError):
    """A stable, client-safe invalid-input error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContextNotFoundError(LookupError):
    """A project-scoped item could not be found."""

    def __init__(self, resource: str) -> None:
        super().__init__(resource)
        self.resource = resource


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ContextService:
    """SQLite-backed MVP service; no network, embeddings, or GraphRAG."""

    def __init__(
        self,
        root: Path,
        chunk_size: int = 800,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.uploads = root / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "context.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.chunk_size = chunk_size
        self.max_upload_bytes = max_upload_bytes
        self._migrate()

    def _migrate(self) -> None:
        self.db.executescript(
            """
            create table if not exists schema_migrations (version integer primary key, applied_at text not null);
            create table if not exists sources (
                id text primary key, project_id text not null, filename text not null,
                media_type text not null, sha256 text not null, path text not null,
                imported_at text not null, status text not null, unique(project_id, sha256)
            );
            create table if not exists chunks (
                id text primary key, project_id text not null, source_id text not null,
                idx integer not null, start integer not null, finish integer not null,
                heading text, text text not null
            );
            create table if not exists evidence (
                id text primary key, project_id text not null, source_id text not null,
                chunk_id text not null, excerpt text not null, relation text not null,
                status text not null, verified_by text, note text, verified_at text
            );
            create table if not exists bundles (
                id text primary key, project_id text not null, task_ref text not null,
                body text not null, created_at text not null
            );
            """
        )
        self._migrate_legacy_project_scope()
        self.db.executescript(
            """
            create index if not exists idx_sources_project on sources(project_id, imported_at);
            create index if not exists idx_chunks_project_source on chunks(project_id, source_id, idx);
            create index if not exists idx_evidence_project on evidence(project_id, source_id, chunk_id);
            create index if not exists idx_bundles_project on bundles(project_id, created_at);
            """
        )
        self.db.execute(
            "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
            (1, _now()),
        )
        self.db.commit()

    def _migrate_legacy_project_scope(self) -> None:
        source_columns = self._columns("sources")
        if source_columns and "project_id" not in source_columns:
            self.db.executescript(
                """
                alter table sources rename to sources_legacy;
                create table sources (
                    id text primary key, project_id text not null, filename text not null,
                    media_type text not null, sha256 text not null, path text not null,
                    imported_at text not null, status text not null, unique(project_id, sha256)
                );
                insert into sources select id, 'default', filename, media_type, sha256, path, imported_at, status from sources_legacy;
                drop table sources_legacy;
                """
            )
        for table in ("chunks", "evidence", "bundles"):
            columns = self._columns(table)
            if columns and "project_id" not in columns:
                self.db.execute(
                    f"alter table {table} add column project_id text not null default 'default'"
                )

    def _columns(self, table: str) -> set[str]:
        return {row[1] for row in self.db.execute(f"pragma table_info({table})")}

    def import_bytes(self, project_id: str, filename: str, content: bytes) -> SourceDocument:
        suffix = Path(filename).suffix.lower()
        media_by_suffix: dict[
            str,
            Literal["text/markdown", "text/plain", "application/json", "application/pdf"],
        ] = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".json": "application/json",
            ".pdf": "application/pdf",
        }
        media = media_by_suffix.get(suffix)
        if media is None:
            raise ContextInputError(
                "unsupported_file_type",
                "Only .md, .txt, .json, and text-extractable .pdf files are supported",
            )
        if not content:
            raise ContextInputError("empty_file", "Uploaded file must not be empty")
        if len(content) > self.max_upload_bytes:
            limit_mb = self.max_upload_bytes / (1024 * 1024)
            raise ContextInputError(
                "file_too_large",
                f"Uploaded file exceeds the {limit_mb:g} MB limit",
            )
        if suffix == ".pdf":
            normalized_text = self._extract_pdf_text(content)
            is_demo_seed = DEMO_MARKER in normalized_text
        else:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ContextInputError("invalid_utf8", "Uploaded text must be valid UTF-8") from error
            normalized_text = decoded
            is_demo_seed = DEMO_MARKER in decoded
        if suffix == ".json":
            try:
                payload = json.loads(decoded)
            except json.JSONDecodeError as error:
                raise ContextInputError("invalid_json", "Uploaded JSON is invalid") from error
            normalized_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            is_demo_seed = isinstance(payload, dict) and payload.get("stem_sci_demo_seed") is True
        status = (
            VerificationStatus.DEMO_SEED
            if is_demo_seed
            else VerificationStatus.MODEL_GENERATED_UNVERIFIED
        )
        sha256 = hashlib.sha256(content).hexdigest()
        existing = self.db.execute(
            "select * from sources where project_id=? and sha256=?",
            (project_id, sha256),
        ).fetchone()
        if existing is not None:
            return self._source(existing)
        source_id = f"src_{uuid4().hex}"
        destination = self.uploads / project_id / f"{sha256}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        imported_at = _now()
        safe_filename = Path(filename.replace("\\", "/")).name
        self.db.execute(
            "insert into sources values (?,?,?,?,?,?,?,?)",
            (source_id, project_id, safe_filename, media, sha256, str(destination), imported_at, status.value),
        )
        for index, start in enumerate(range(0, len(normalized_text), self.chunk_size)):
            part = normalized_text[start : start + self.chunk_size]
            chunk_id = f"chk_{uuid4().hex}"
            evidence_id = f"evd_{uuid4().hex}"
            heading = next(
                (
                    line.removeprefix("#").strip()
                    for line in reversed(normalized_text[: start + 1].splitlines())
                    if line.startswith("#")
                ),
                None,
            )
            self.db.execute(
                "insert into chunks values (?,?,?,?,?,?,?,?)",
                (chunk_id, project_id, source_id, index, start, start + len(part), heading, part),
            )
            self.db.execute(
                "insert into evidence values (?,?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id,
                    project_id,
                    source_id,
                    chunk_id,
                    part[:280],
                    "mentioning",
                    status.value,
                    None,
                    None,
                    None,
                ),
            )
        self.db.commit()
        return SourceDocument(
            source_id=source_id,
            project_id=project_id,
            filename=safe_filename,
            media_type=media,
            sha256=sha256,
            storage_path=str(destination),
            imported_at=imported_at,
            verification_status=status,
        )

    def _extract_pdf_text(self, content: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ContextInputError(
                    "encrypted_pdf",
                    "Encrypted PDFs cannot be imported without an approved decryption workflow",
                )
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except ContextInputError:
            raise
        except Exception as error:
            raise ContextInputError("invalid_pdf", "Uploaded PDF could not be read") from error
        if not text:
            raise ContextInputError(
                "pdf_without_extractable_text",
                "PDF has no extractable text; OCR support is not available in this MVP",
            )
        return text

    def _source(self, row: sqlite3.Row) -> SourceDocument:
        return SourceDocument(
            source_id=row["id"],
            project_id=row["project_id"],
            filename=row["filename"],
            media_type=row["media_type"],
            sha256=row["sha256"],
            storage_path=row["path"],
            imported_at=row["imported_at"],
            verification_status=row["status"],
        )

    def list_sources(self, project_id: str) -> list[SourceDocument]:
        rows = self.db.execute(
            "select * from sources where project_id=? order by imported_at desc, id asc",
            (project_id,),
        )
        return [self._source(row) for row in rows]

    def get_source(self, project_id: str, source_id: str) -> SourceDocument:
        row = self.db.execute(
            "select * from sources where project_id=? and id=?",
            (project_id, source_id),
        ).fetchone()
        if row is None:
            raise ContextNotFoundError("source")
        return self._source(row)

    def chunks(self, project_id: str, source_id: str) -> list[SourceChunk]:
        self.get_source(project_id, source_id)
        rows = self.db.execute(
            "select * from chunks where project_id=? and source_id=? order by idx",
            (project_id, source_id),
        )
        return [self._chunk(row) for row in rows]

    def _chunk(self, row: sqlite3.Row) -> SourceChunk:
        return SourceChunk(
            chunk_id=row["id"],
            project_id=row["project_id"],
            source_id=row["source_id"],
            text=row["text"],
            location=SourceLocation(
                chunk_index=row["idx"],
                char_start=row["start"],
                char_end=row["finish"],
                heading=row["heading"],
            ),
        )

    def evidence_ref(self, row: sqlite3.Row) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=row["id"],
            project_id=row["project_id"],
            source_id=row["source_id"],
            chunk_id=row["chunk_id"],
            excerpt=row["excerpt"],
            location=SourceLocation(
                chunk_index=row["idx"],
                char_start=row["start"],
                char_end=row["finish"],
                heading=row["heading"],
            ),
            verification_status=row["status"],
        )

    def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        terms = [term.lower() for term in request.query.split() if term]
        rows = self.db.execute(
            """
            select e.*, c.idx, c.start, c.finish, c.heading, c.text
            from evidence e join chunks c on e.chunk_id=c.id
            where e.project_id=? and c.project_id=?
            """,
            (request.project_id, request.project_id),
        ).fetchall()
        allowed = {status.value for status in request.allowed_verification_statuses}
        found: list[EvidenceSearchResult] = []
        for row in rows:
            if allowed and row["status"] not in allowed:
                continue
            score = sum(row["text"].lower().count(term) for term in terms)
            if score:
                found.append(
                    EvidenceSearchResult(evidence=self.evidence_ref(row), score=float(score))
                )
        return sorted(
            found,
            key=lambda result: (
                -result.score,
                STATUS_ORDER[result.evidence.verification_status.value],
                result.evidence.source_id,
                result.evidence.location.chunk_index,
            ),
        )[: request.limit]

    def verify_source(
        self,
        project_id: str,
        evidence_id: str,
        verified_by: str,
        note: str,
    ) -> EvidenceRef:
        if not verified_by or not note:
            raise ContextInputError(
                "missing_verification_metadata",
                "verified_by and verification_note are required",
            )
        row = self._evidence_row(project_id, evidence_id)
        if row is None:
            raise ContextNotFoundError("evidence")
        self.db.execute(
            """
            update evidence set status=?, verified_by=?, note=?, verified_at=?
            where project_id=? and id=?
            """,
            (
                VerificationStatus.SOURCE_VERIFIED.value,
                verified_by,
                note,
                _now(),
                project_id,
                evidence_id,
            ),
        )
        self.db.commit()
        verified = self._evidence_row(project_id, evidence_id)
        if verified is None:
            raise ContextNotFoundError("evidence")
        return self.evidence_ref(verified)

    def _evidence_row(self, project_id: str, evidence_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.db.execute(
                """
                select e.*, c.idx, c.start, c.finish, c.heading, c.text
                from evidence e join chunks c on e.chunk_id=c.id
                where e.project_id=? and c.project_id=? and e.id=?
                """,
                (project_id, project_id, evidence_id),
            ).fetchone(),
        )

    def get_evidence(self, project_id: str, evidence_id: str) -> EvidenceDetail:
        row = self._evidence_row(project_id, evidence_id)
        if row is None:
            raise ContextNotFoundError("evidence")
        reference = self.evidence_ref(row)
        return EvidenceDetail(
            **reference.model_dump(),
            relation=row["relation"],
            verification_note=row["note"],
            verified_by=row["verified_by"],
            verified_at=row["verified_at"],
        )

    def build(self, request: ContextBuildRequest) -> ContextBundle:
        results = self.search(
            EvidenceSearchRequest(
                project_id=request.project_id,
                query=request.query,
                limit=50,
                allowed_verification_statuses=request.allowed_verification_statuses,
            )
        )
        results.sort(
            key=lambda result: (
                STATUS_ORDER[result.evidence.verification_status.value],
                -result.score,
                result.evidence.source_id,
                result.evidence.location.chunk_index,
            )
        )
        selected: list[EvidenceRef] = []
        used = 0
        chunks_per_source: dict[str, int] = {}
        for result in results:
            evidence = result.evidence
            if chunks_per_source.get(evidence.source_id, 0) >= request.max_chunks_per_source:
                continue
            token_cost = max(1, len(evidence.excerpt) // 4)
            if used + token_cost > request.token_budget:
                continue
            selected.append(evidence)
            used += token_cost
            chunks_per_source[evidence.source_id] = chunks_per_source.get(evidence.source_id, 0) + 1
        summary = {
            status.value: sum(ref.verification_status == status for ref in selected)
            for status in VerificationStatus
        }
        canonical = json.dumps(
            {
                "project_id": request.project_id,
                "task_ref": request.task_ref,
                "query": request.query,
                "evidence": [ref.evidence_id for ref in selected],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        bundle = ContextBundle(
            context_id=f"ctx_{uuid4().hex}",
            project_id=request.project_id,
            task_ref=request.task_ref,
            query=request.query,
            evidence_refs=selected,
            source_refs=sorted(chunks_per_source),
            unresolved_questions=[] if selected else ["No eligible evidence matched the query"],
            risk_flags=[] if selected else ["insufficient_verified_evidence"],
            verification_summary=summary,
            token_budget=request.token_budget,
            estimated_tokens=used,
            context_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            generated_at=_now(),
        )
        self.persist_bundle(bundle)
        return bundle

    def persist_bundle(self, bundle: ContextBundle) -> ContextBundle:
        """Persist a fully formed ContextBundle without storing raw corpus files in state."""

        self.db.execute(
            "insert or replace into bundles values (?,?,?,?,?)",
            (
                bundle.context_id,
                bundle.project_id,
                bundle.task_ref,
                bundle.model_dump_json(),
                bundle.generated_at,
            ),
        )
        self.db.commit()
        return bundle

    def get_bundle(self, project_id: str, context_id: str) -> ContextBundle:
        row = self.db.execute(
            "select body from bundles where project_id=? and id=?",
            (project_id, context_id),
        ).fetchone()
        if row is None:
            raise ContextNotFoundError("context bundle")
        return ContextBundle.model_validate_json(row["body"])
