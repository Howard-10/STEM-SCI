"""Research unit-test and rubric contracts; Gate routing remains in the Controller."""

from .models import ResearchTestResult
from .rubric_registry import ResearchRubric, RubricRegistry

__all__ = ["ResearchRubric", "ResearchTestResult", "RubricRegistry"]
