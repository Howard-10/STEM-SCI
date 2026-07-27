"""Local deterministic ingestion, search, verification, and context assembly."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

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


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ContextService:
    """SQLite-backed MVP service; no network, embeddings, or GraphRAG."""

    def __init__(self, root: Path, chunk_size: int = 800) -> None:
        self.root = root
        self.uploads = root / "uploads"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "context.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.chunk_size = chunk_size
        self.db.executescript("""
            create table if not exists sources (id text primary key, filename text, media_type text, sha256 text unique, path text, imported_at text, status text);
            create table if not exists chunks (id text primary key, source_id text, idx integer, start integer, finish integer, heading text, text text);
            create table if not exists evidence (id text primary key, source_id text, chunk_id text, excerpt text, relation text, status text, verified_by text, note text, verified_at text);
            create table if not exists bundles (id text primary key, task_ref text, body text, created_at text);
        """)

    def import_bytes(self, filename: str, content: bytes, status: VerificationStatus = VerificationStatus.MODEL_GENERATED_UNVERIFIED) -> SourceDocument:
        suffix = Path(filename).suffix.lower()
        media_by_suffix: dict[str, Literal["text/markdown", "text/plain", "application/json"]] = {".md": "text/markdown", ".txt": "text/plain", ".json": "application/json"}
        media = media_by_suffix.get(suffix)
        if media is None or not content or len(content) > 2_000_000:
            raise ValueError("Only non-empty .md, .txt, and .json files up to 2 MB are supported")
        sha = hashlib.sha256(content).hexdigest()
        existing = self.db.execute("select * from sources where sha256=?", (sha,)).fetchone()
        if existing:
            return self._source(existing)
        text = json.dumps(json.loads(content), ensure_ascii=False, sort_keys=True, indent=2) if suffix == ".json" else content.decode("utf-8")
        source_id = f"src_{uuid4().hex}"
        destination = self.uploads / f"{sha}{suffix}"
        destination.write_bytes(content)
        now = _now()
        self.db.execute("insert into sources values (?,?,?,?,?,?,?)", (source_id, Path(filename).name, media, sha, str(destination), now, status.value))
        for index, start in enumerate(range(0, len(text), self.chunk_size)):
            part = text[start:start + self.chunk_size]
            chunk_id, evidence_id = f"chk_{uuid4().hex}", f"evd_{uuid4().hex}"
            heading = next((line.removeprefix("#").strip() for line in reversed(text[:start + 1].splitlines()) if line.startswith("#")), None)
            self.db.execute("insert into chunks values (?,?,?,?,?,?,?)", (chunk_id, source_id, index, start, start + len(part), heading, part))
            self.db.execute("insert into evidence values (?,?,?,?,?,?,?,?,?)", (evidence_id, source_id, chunk_id, part[:280], "mentioning", status.value, None, None, None))
        self.db.commit()
        return SourceDocument(source_id=source_id, filename=Path(filename).name, media_type=media, sha256=sha, storage_path=str(destination), imported_at=now, verification_status=status)

    def _source(self, row: sqlite3.Row) -> SourceDocument:
        return SourceDocument(source_id=row["id"], filename=row["filename"], media_type=row["media_type"], sha256=row["sha256"], storage_path=row["path"], imported_at=row["imported_at"], verification_status=row["status"])

    def list_sources(self) -> list[SourceDocument]:
        return [self._source(row) for row in self.db.execute("select * from sources order by imported_at desc")]

    def get_source(self, source_id: str) -> SourceDocument:
        row = self.db.execute("select * from sources where id=?", (source_id,)).fetchone()
        if row is None:
            raise KeyError(source_id)
        return self._source(row)

    def chunks(self, source_id: str) -> list[SourceChunk]:
        self.get_source(source_id)
        return [SourceChunk(chunk_id=row["id"], source_id=row["source_id"], text=row["text"], location=SourceLocation(chunk_index=row["idx"], char_start=row["start"], char_end=row["finish"], heading=row["heading"])) for row in self.db.execute("select * from chunks where source_id=? order by idx", (source_id,))]

    def evidence_ref(self, row: sqlite3.Row) -> EvidenceRef:
        return EvidenceRef(evidence_id=row["id"], source_id=row["source_id"], chunk_id=row["chunk_id"], excerpt=row["excerpt"], location=SourceLocation(chunk_index=row["idx"], char_start=row["start"], char_end=row["finish"], heading=row["heading"]), verification_status=row["status"])

    def search(self, request: EvidenceSearchRequest) -> list[EvidenceSearchResult]:
        terms = [term.lower() for term in request.query.split() if term]
        rows = self.db.execute("select e.*, c.idx,c.start,c.finish,c.heading,c.text from evidence e join chunks c on e.chunk_id=c.id").fetchall()
        found = []
        for row in rows:
            if request.allowed_verification_statuses and row["status"] not in [s.value for s in request.allowed_verification_statuses]: continue
            score = sum(row["text"].lower().count(term) for term in terms)
            if score: found.append(EvidenceSearchResult(evidence=self.evidence_ref(row), score=float(score)))
        return sorted(found, key=lambda item: item.score, reverse=True)[:request.limit]

    def verify_source(self, evidence_id: str, verified_by: str, note: str) -> EvidenceRef:
        if not verified_by or not note: raise ValueError("verified_by and verification_note are required")
        self.db.execute("update evidence set status=?,verified_by=?,note=?,verified_at=? where id=?", (VerificationStatus.SOURCE_VERIFIED.value, verified_by, note, _now(), evidence_id))
        self.db.commit(); row = self._evidence_row(evidence_id)
        if row is None: raise KeyError(evidence_id)
        return self.evidence_ref(row)

    def _evidence_row(self, evidence_id: str) -> sqlite3.Row | None:
        return cast(sqlite3.Row | None, self.db.execute("select e.*, c.idx,c.start,c.finish,c.heading,c.text from evidence e join chunks c on e.chunk_id=c.id where e.id=?", (evidence_id,)).fetchone())

    def get_evidence(self, evidence_id: str) -> EvidenceDetail:
        row = self._evidence_row(evidence_id)
        if row is None:
            raise KeyError(evidence_id)
        reference = self.evidence_ref(row)
        return EvidenceDetail(**reference.model_dump(), relation=row["relation"], verification_note=row["note"], verified_by=row["verified_by"], verified_at=row["verified_at"])

    def build(self, request: ContextBuildRequest) -> ContextBundle:
        results = self.search(EvidenceSearchRequest(query=request.query, limit=50, allowed_verification_statuses=request.allowed_verification_statuses))
        selected, used, sources = [], 0, set()
        for result in results:
            cost = max(1, len(result.evidence.excerpt) // 4)
            if used + cost > request.token_budget: continue
            selected.append(result.evidence); used += cost; sources.add(result.evidence.source_id)
        summary = {status.value: sum(ref.verification_status == status for ref in selected) for status in VerificationStatus}
        canonical = json.dumps({"task": request.task_ref, "query": request.query, "evidence": [r.evidence_id for r in selected]}, sort_keys=True)
        bundle = ContextBundle(context_id=f"ctx_{uuid4().hex}", task_ref=request.task_ref, query=request.query, evidence_refs=selected, source_refs=sorted(sources), unresolved_questions=[] if selected else ["No eligible evidence matched the query"], risk_flags=[] if selected else ["insufficient_verified_evidence"], verification_summary=summary, token_budget=request.token_budget, estimated_tokens=used, context_hash=hashlib.sha256(canonical.encode()).hexdigest(), generated_at=_now())
        self.db.execute("insert into bundles values (?,?,?,?)", (bundle.context_id, bundle.task_ref, bundle.model_dump_json(), bundle.generated_at)); self.db.commit()
        return bundle

    def get_bundle(self, context_id: str) -> ContextBundle:
        row = self.db.execute("select body from bundles where id=?", (context_id,)).fetchone()
        if row is None: raise KeyError(context_id)
        return ContextBundle.model_validate_json(row["body"])
