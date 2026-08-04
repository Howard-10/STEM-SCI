from datetime import UTC, datetime

import pytest

from stem_sci.artifacts.decision_store import InMemoryDecisionStore
from stem_sci.core.models import ApprovalRecord


def test_approval_store_rejects_cross_project_idempotency_reuse() -> None:
    store = InMemoryDecisionStore()
    base = {
        "artifact_id": "artifact-1",
        "artifact_version": 1,
        "decision": "approved",
        "decided_by": "researcher",
        "decided_at": datetime.now(UTC),
        "idempotency_key": "same-project-key",
    }
    store.put(ApprovalRecord(approval_id="approval-1", project_id="project-a", **base))
    store.put(ApprovalRecord(approval_id="approval-2", project_id="project-b", **base))
    assert len(store.list_project("project-a")) == 1


def test_approval_record_requires_decider_and_project() -> None:
    with pytest.raises(ValueError):
        ApprovalRecord(
            approval_id="approval-invalid",
            project_id="",
            artifact_id="artifact-1",
            artifact_version=1,
            decision="approved",
            decided_by="researcher",
            decided_at=datetime.now(UTC),
            idempotency_key="key",
        )
