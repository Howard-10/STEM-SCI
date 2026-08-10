"""Confirmed long-term memory backed by a LangGraph Store."""

from __future__ import annotations

import re
from collections.abc import Iterable
from threading import RLock
from typing import TYPE_CHECKING

from stem_sci.compat.langgraph import BaseStore, InMemoryStore

from .models import (
    MemoryCandidate,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryStatus,
    Sensitivity,
    utc_now,
)
from .policy import classify_sensitivity

if TYPE_CHECKING:
    from stem_sci.context.models import RuntimeContext


class MemoryPolicyError(ValueError):
    """Raised when a write violates confirmation, scope, or privacy rules."""


def _terms(text: str) -> set[str]:
    lowered = text.casefold()
    words = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", lowered))
    words.update(lowered[index : index + 2] for index in range(max(0, len(lowered) - 1)))
    return words


class LongTermMemory:
    """Controls proposals and confirmed records without mixing them with evidence."""

    def __init__(self, store: BaseStore | None = None) -> None:
        self.store = store or InMemoryStore()
        self._candidates: dict[tuple[str, str, str], MemoryCandidate] = {}
        self._lock = RLock()

    @staticmethod
    def _user_namespace(user_id: str) -> tuple[str, ...]:
        return ("users", user_id, "profile")

    @staticmethod
    def _project_namespace(user_id: str, project_id: str) -> tuple[str, ...]:
        return ("users", user_id, "projects", project_id, "memory")

    def add_candidates(
        self, identity: RuntimeContext, candidates: Iterable[MemoryCandidate]
    ) -> list[MemoryCandidate]:
        accepted = []
        with self._lock:
            for candidate in candidates:
                sensitivity = classify_sensitivity(candidate.content)
                if sensitivity is Sensitivity.PROHIBITED:
                    continue
                normalized = candidate.model_copy(update={"sensitivity": sensitivity})
                key = (identity.user_id, identity.project_id, normalized.memory_id)
                self._candidates[key] = normalized
                accepted.append(normalized)
        return accepted

    def confirm(self, identity: RuntimeContext, memory_id: str) -> MemoryRecord:
        key = (identity.user_id, identity.project_id, memory_id)
        with self._lock:
            candidate = self._candidates.pop(key, None)
        if candidate is None:
            raise MemoryPolicyError("Unknown candidate in this user/project scope")
        if classify_sensitivity(candidate.content) is Sensitivity.PROHIBITED:
            raise MemoryPolicyError("Sensitive or prohibited information cannot be stored")
        project_id = identity.project_id if candidate.scope is MemoryScope.PROJECT else None
        record = MemoryRecord(
            memory_id=candidate.memory_id,
            user_id=identity.user_id,
            project_id=project_id,
            scope=candidate.scope,
            kind=candidate.kind,
            content=candidate.content,
            source_message_ids=candidate.source_message_ids,
            sensitivity=candidate.sensitivity,
        )
        namespace = self._namespace_for_record(record, identity.project_id)
        self.store.put(namespace, record.memory_id, record.model_dump(mode="json"))
        return record

    def recall(self, identity: RuntimeContext, query: str, limit: int = 6) -> list[MemoryRecord]:
        if limit < 1:
            return []
        records: list[MemoryRecord] = []
        namespaces = [
            self._user_namespace(identity.user_id),
            self._project_namespace(identity.user_id, identity.project_id),
        ]
        for namespace in namespaces:
            for item in self.store.search(namespace):
                record = MemoryRecord.model_validate(item.value)
                if record.status is MemoryStatus.CONFIRMED:
                    records.append(record)
        query_terms = _terms(query)

        def score(record: MemoryRecord) -> tuple[float, str]:
            overlap = len(query_terms & _terms(record.content)) / max(1, len(query_terms))
            preference_boost = 0.12 if record.kind is MemoryKind.USER_PREFERENCE else 0.0
            project_boost = 0.05 if record.scope is MemoryScope.PROJECT else 0.0
            return overlap + preference_boost + project_boost, record.updated_at.isoformat()

        records.sort(key=score, reverse=True)
        return records[:limit]

    def correct(self, identity: RuntimeContext, memory_id: str, content: str) -> MemoryRecord:
        existing, namespace = self._get_owned(identity, memory_id)
        if classify_sensitivity(content) is Sensitivity.PROHIBITED:
            raise MemoryPolicyError("Sensitive or prohibited information cannot be stored")
        corrected = existing.model_copy(
            update={
                "content": content,
                "version": existing.version + 1,
                "updated_at": utc_now(),
            }
        )
        self.store.put(namespace, memory_id, corrected.model_dump(mode="json"))
        return corrected

    def forget(self, identity: RuntimeContext, memory_id: str) -> None:
        _, namespace = self._get_owned(identity, memory_id)
        self.store.delete(namespace, memory_id)

    def clear_project(self, identity: RuntimeContext) -> int:
        namespace = self._project_namespace(identity.user_id, identity.project_id)
        items = list(self.store.search(namespace))
        for item in items:
            self.store.delete(namespace, item.key)
        return len(items)

    def _get_owned(
        self, identity: RuntimeContext, memory_id: str
    ) -> tuple[MemoryRecord, tuple[str, ...]]:
        for namespace in (
            self._user_namespace(identity.user_id),
            self._project_namespace(identity.user_id, identity.project_id),
        ):
            item = self.store.get(namespace, memory_id)
            if item is not None:
                record = MemoryRecord.model_validate(item.value)
                if record.user_id != identity.user_id:
                    break
                if record.scope is MemoryScope.PROJECT and record.project_id != identity.project_id:
                    break
                return record, namespace
        raise MemoryPolicyError("Memory not found in this user/project scope")

    def _namespace_for_record(
        self, record: MemoryRecord, active_project_id: str
    ) -> tuple[str, ...]:
        if record.scope is MemoryScope.USER:
            return self._user_namespace(record.user_id)
        return self._project_namespace(record.user_id, active_project_id)
