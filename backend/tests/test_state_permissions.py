"""Reserved Phase 1 invariant tests for Controller-only state transitions."""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 1 model not implemented yet")


def test_state_permission_invariant_placeholder() -> None:
    """Reserved until the Phase 1 state model is approved and implemented."""
    raise AssertionError("The module-level skip should prevent execution.")
