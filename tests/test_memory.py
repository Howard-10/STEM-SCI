"""Memory confirmation, privacy, and isolation invariants."""

import pytest

from stem_sci.compat.langchain import HumanMessage
from stem_sci.context.models import RuntimeContext
from stem_sci.memory.long_term import LongTermMemory, MemoryPolicyError
from stem_sci.memory.models import MemoryCandidate, MemoryKind, MemoryScope
from stem_sci.memory.proposer import MemoryProposer


def identity(user: str = "u1", project: str = "p1") -> RuntimeContext:
    return RuntimeContext(user_id=user, project_id=project, thread_id="t1", run_id="r1")


def test_candidate_is_not_recalled_until_confirmed() -> None:
    memory = LongTermMemory()
    candidate = MemoryCandidate(
        scope=MemoryScope.USER,
        kind=MemoryKind.USER_PREFERENCE,
        content="I prefer concise answers",
    )
    memory.add_candidates(identity(), [candidate])
    assert memory.recall(identity(), "concise") == []
    confirmed = memory.confirm(identity(), candidate.memory_id)
    assert memory.recall(identity(), "concise")[0].memory_id == confirmed.memory_id


def test_user_and_project_scopes_are_isolated() -> None:
    memory = LongTermMemory()
    candidate = MemoryCandidate(
        scope=MemoryScope.PROJECT,
        kind=MemoryKind.APPROVED_DECISION,
        content="Approved quasi-experimental design",
    )
    memory.add_candidates(identity(), [candidate])
    memory.confirm(identity(), candidate.memory_id)
    assert memory.recall(identity(user="u2"), "design") == []
    assert memory.recall(identity(project="p2"), "design") == []
    assert memory.recall(identity(), "design")


def test_sensitive_memory_is_rejected_and_cannot_be_confirmed() -> None:
    memory = LongTermMemory()
    candidate = MemoryCandidate(
        scope=MemoryScope.USER,
        kind=MemoryKind.USER_PREFERENCE,
        content="My API key: sk-secretvalue123456789",
    )
    assert memory.add_candidates(identity(), [candidate]) == []
    with pytest.raises(MemoryPolicyError):
        memory.confirm(identity(), candidate.memory_id)


def test_correction_and_forgetting_are_user_controlled() -> None:
    memory = LongTermMemory()
    candidate = MemoryCandidate(
        scope=MemoryScope.USER,
        kind=MemoryKind.USER_PREFERENCE,
        content="I prefer concise answers",
    )
    memory.add_candidates(identity(), [candidate])
    memory.confirm(identity(), candidate.memory_id)
    corrected = memory.correct(identity(), candidate.memory_id, "I prefer detailed answers")
    assert corrected.version == 2
    assert memory.recall(identity(), "detailed")[0].content == "I prefer detailed answers"
    memory.forget(identity(), candidate.memory_id)
    assert memory.recall(identity(), "detailed") == []


def test_proposer_only_extracts_explicit_statements_and_degrades_safely() -> None:
    messages = [HumanMessage(content="Please always answer in English", id="m1")]
    candidates = MemoryProposer().propose(messages)
    assert len(candidates) == 1
    assert candidates[0].scope is MemoryScope.USER

    class BrokenModel:
        def with_structured_output(self, schema):
            raise RuntimeError("offline")

    assert MemoryProposer(model=BrokenModel(), max_retries=1).propose(messages) == []
