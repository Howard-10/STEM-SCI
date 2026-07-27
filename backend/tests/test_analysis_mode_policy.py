"""Reserved Phase 1 invariant tests for analysis execution modes."""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 1 model not implemented yet")


def test_analysis_mode_policy_placeholder() -> None:
    """Reserved until Phase 1 analysis-mode contracts are implemented."""
    raise AssertionError("The module-level skip should prevent execution.")
