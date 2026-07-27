"""Reserved Phase 1 invariant tests for dataset-version safety."""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 1 model not implemented yet")


def test_dataset_invariant_placeholder() -> None:
    """Reserved until Phase 1 data contracts are implemented."""
    raise AssertionError("The module-level skip should prevent execution.")
