"""Conversation memory store for the QA chain."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import ContextMode
from .qa_models import ConversationSummary, MemoryTurn, QAReference


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
                mode text not null default 'discovery',
                citations_json text not null,
                retrieval_trace_ref text,
                created_at text not null
            );
            create index if not exists idx_qa_memory_conversation
                on qa_memory_turns(conversation_id, created_at desc, memory_id desc);
            create index if not exists idx_qa_memory_project
                on qa_memory_turns(project_id, created_at desc, conversation_id);
            """
        )
        columns = {
            str(row["name"])
            for row in self.db.execute("pragma table_info(qa_memory_turns)").fetchall()
        }
        if "mode" not in columns:
            self.db.execute(
                "alter table qa_memory_turns add column mode text not null default 'discovery'"
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
        mode: ContextMode = ContextMode.DISCOVERY,
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
                answer, route, mode, citations_json, retrieval_trace_ref, created_at
            ) values (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                conversation_id,
                project_id,
                question,
                rewritten_query,
                answer,
                route,
                mode.value,
                citations_json,
                retrieval_trace_ref,
                created_at,
            ),
        )
        self.db.commit()
        return MemoryTurn(
            memory_id=memory_id,
            turn_id=memory_id,
            mode=mode,
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

    def recent_turns(
        self,
        conversation_id: str,
        limit: int = 6,
        project_id: str | None = None,
    ) -> list[MemoryTurn]:
        where = "conversation_id=?"
        params: list[object] = [conversation_id]
        if project_id is not None:
            where += " and project_id=?"
            params.append(project_id)
        params.append(limit)
        rows = self.db.execute(
            f"""
            select * from qa_memory_turns
            where {where}
            order by created_at desc, memory_id desc
            limit ?
            """,
            params,
        ).fetchall()
        return list(reversed([self._turn(row) for row in rows]))

    def conversation_turns(
        self,
        *,
        project_id: str,
        conversation_id: str,
        limit: int = 100,
    ) -> list[MemoryTurn]:
        rows = self.db.execute(
            """
            select * from qa_memory_turns
            where project_id=? and conversation_id=?
            order by created_at asc, memory_id asc
            limit ?
            """,
            (project_id, conversation_id, limit),
        ).fetchall()
        return [self._turn(row) for row in rows]

    def list_conversations(self, project_id: str, limit: int = 50) -> list[ConversationSummary]:
        rows = self.db.execute(
            """
            select
                conversation_id,
                project_id,
                min(created_at) as created_at,
                max(created_at) as updated_at,
                count(*) as turn_count
            from qa_memory_turns
            where project_id=?
            group by conversation_id, project_id
            order by updated_at desc, conversation_id desc
            limit ?
            """,
            (project_id, limit),
        ).fetchall()
        summaries: list[ConversationSummary] = []
        for row in rows:
            last = self.db.execute(
                """
                select question, answer from qa_memory_turns
                where project_id=? and conversation_id=?
                order by created_at desc, memory_id desc
                limit 1
                """,
                (project_id, row["conversation_id"]),
            ).fetchone()
            if last is None:
                continue
            title = _preview(str(last["question"]), 48)
            summaries.append(
                ConversationSummary(
                    conversation_id=str(row["conversation_id"]),
                    project_id=str(row["project_id"]),
                    title=title,
                    last_question=str(last["question"]),
                    last_answer_preview=_preview(str(last["answer"]), 160),
                    turn_count=int(row["turn_count"]),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                )
            )
        return summaries

    @staticmethod
    def _turn(row: sqlite3.Row) -> MemoryTurn:
        citations = json.loads(row["citations_json"])
        return MemoryTurn(
            memory_id=row["memory_id"],
            turn_id=row["memory_id"],
            mode=ContextMode(str(row["mode"] or ContextMode.DISCOVERY)),
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


def _preview(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 1)].rstrip()}…"
