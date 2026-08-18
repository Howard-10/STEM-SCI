from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stem_sci.agents import AgentResult
from stem_sci.core.state import ResearchState


def test_agent_result_cannot_carry_controller_stage_mutation() -> None:
    with pytest.raises(ValidationError):
        AgentResult(
            agent_run_id="run-1", agent_id="mentor_planning", agent_version="v1",
            created_at=datetime.now(UTC), new_current_stage="RELEASED"
        )


def test_research_state_rejects_unknown_governance_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchState(project_id="permission-demo", approved=True)
