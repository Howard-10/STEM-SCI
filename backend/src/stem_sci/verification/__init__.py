"""Research unit-test contracts; Gate routing remains in the Controller."""
"""Research-test and rubric contracts."""

from .models import ResearchTestResult
from .rubric_registry import ResearchRubric, RubricRegistry

__all__ = ["ResearchRubric", "ResearchTestResult", "RubricRegistry"]
