"""Approved-decision scope and isolation invariants."""

import pytest

from stem_sci.artifacts.decision_store import DecisionRecord, DecisionStore
from stem_sci.context.models import RuntimeContext


def identity(user: str = "u1", project: str = "p1") -> RuntimeContext:
    return RuntimeContext(user_id=user, project_id=project, thread_id="t", run_id="r")


def test_decision_store_is_project_isolated() -> None:
    store = DecisionStore()
    decision = DecisionRecord(
        user_id="u1",
        project_id="p1",
        stage="design",
        content="Use a quasi-experiment",
        decided_by="researcher",
    )
    store.save(identity(), decision)
    assert store.get(identity(), decision.decision_id).content == decision.content
    with pytest.raises(KeyError):
        store.get(identity(project="p2"), decision.decision_id)
    with pytest.raises(ValueError):
        store.save(identity(user="u2"), decision)
