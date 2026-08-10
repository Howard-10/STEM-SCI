"""Stable public memory API for future controllers and agents."""

from __future__ import annotations

from collections.abc import Sequence

from stem_sci.compat.langchain import BaseMessage
from stem_sci.context.models import RuntimeContext

from .long_term import LongTermMemory
from .models import ConversationSummary, MemoryCandidate, MemoryRecord
from .proposer import MemoryProposer
from .short_term import ShortTermMemory

_LONG_TERM = LongTermMemory()
_SHORT_TERM = ShortTermMemory()
_PROPOSER = MemoryProposer()


def propose_memories(
    identity: RuntimeContext, messages: Sequence[BaseMessage]
) -> list[MemoryCandidate]:
    return _LONG_TERM.add_candidates(identity, _PROPOSER.propose(messages))


def confirm_memory(identity: RuntimeContext, memory_id: str) -> MemoryRecord:
    return _LONG_TERM.confirm(identity, memory_id)


def recall_memories(identity: RuntimeContext, query: str, limit: int = 6) -> list[MemoryRecord]:
    return _LONG_TERM.recall(identity, query, limit)


def correct_memory(identity: RuntimeContext, memory_id: str, content: str) -> MemoryRecord:
    return _LONG_TERM.correct(identity, memory_id, content)


def forget_memory(identity: RuntimeContext, memory_id: str) -> None:
    _LONG_TERM.forget(identity, memory_id)


def clear_project_memory(identity: RuntimeContext) -> int:
    return _LONG_TERM.clear_project(identity)


def append_thread_messages(identity: RuntimeContext, messages: Sequence[BaseMessage]) -> None:
    _SHORT_TERM.append(identity, messages)


def summarize_thread(identity: RuntimeContext, force: bool = False) -> ConversationSummary:
    return _SHORT_TERM.summarize(identity, force=force)
