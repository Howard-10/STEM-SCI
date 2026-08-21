"""Conversation memory store for the QA chain."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .qa_models import MemoryTurn, QAReference


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationMemoryStore:
    """Small SQLite memory store that keeps the chat chain traceable."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "qa_memory.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.db.executescript(
            """
            create table if not exists qa_memory_turns (
                memory_id text primary key,
                conversation_id text not null,
                project_id text not null,
                question text not null,
                rewritten_query text not null,
                answer text not null,
                route text not null,
                citations_json text not null,
                retrieval_trace_ref text,
                created_at text not null
            );
            create index if not exists idx_qa_memory_conversation
                on qa_memory_turns(conversation_id, created_at desc, memory_id desc);
            """
        )
        self.db.commit()

    def append_turn(
        self,
        *,
        conversation_id: str,
        project_id: str,
        question: str,
        rewritten_query: str,
        answer: str,
        route: str,
        citations: list[QAReference],
        retrieval_trace_ref: str | None,
    ) -> MemoryTurn:
        memory_id = f"mem_{uuid4().hex}"
        created_at = _now()
        citations_json = json.dumps(
            [citation.model_dump(mode="json") for citation in citations],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self.db.execute(
            """
            insert into qa_memory_turns(
                memory_id, conversation_id, project_id, question, rewritten_query,
                answer, route, citations_json, retrieval_trace_ref, created_at
            ) values (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                conversation_id,
                project_id,
                question,
                rewritten_query,
                answer,
                route,
                citations_json,
                retrieval_trace_ref,
                created_at,
            ),
        )
        self.db.commit()
        return MemoryTurn(
            memory_id=memory_id,
            conversation_id=conversation_id,
            project_id=project_id,
            question=question,
            rewritten_query=rewritten_query,
            answer=answer,
            route=route,
            citations=citations,
            retrieval_trace_ref=retrieval_trace_ref,
            created_at=created_at,
        )

    def recent_turns(self, conversation_id: str, limit: int = 6) -> list[MemoryTurn]:
        rows = self.db.execute(
            """
            select * from qa_memory_turns
            where conversation_id=?
            order by created_at desc, memory_id desc
            limit ?
            """,
            (conversation_id, limit),
        ).fetchall()
        turns: list[MemoryTurn] = []
        for row in rows:
            citations = json.loads(row["citations_json"])
            turns.append(
                MemoryTurn(
                    memory_id=row["memory_id"],
                    conversation_id=row["conversation_id"],
                    project_id=row["project_id"],
                    question=row["question"],
                    rewritten_query=row["rewritten_query"],
                    answer=row["answer"],
                    route=row["route"],
                    citations=[QAReference.model_validate(item) for item in citations],
                    retrieval_trace_ref=row["retrieval_trace_ref"],
                    created_at=row["created_at"],
                )
            )
        return list(reversed(turns))
