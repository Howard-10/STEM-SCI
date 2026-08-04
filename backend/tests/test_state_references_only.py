import pytest
from pydantic import ValidationError

from stem_sci.core.state import ResearchState


def test_research_state_contains_references_not_large_payloads() -> None:
    state = ResearchState(project_id="reference-demo", evidence_refs=["evidence://1"])
    assert state.evidence_refs == ["evidence://1"]
    with pytest.raises(ValidationError):
        ResearchState(project_id="reference-demo", full_pdf="not allowed")
