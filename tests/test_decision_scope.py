"""Reserved Phase 1 invariant tests for scoped blocking decisions."""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 1 model not implemented yet")


def test_decision_scope_invariant_placeholder() -> None:
    """Reserved until Phase 1 decision-scope contracts are implemented."""
    raise AssertionError("The module-level skip should prevent execution.")
