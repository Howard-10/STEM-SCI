"""Reference-only research-test result contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from stem_sci.core.models import DomainModel


class ResearchTestResult(DomainModel):
    test_result_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    target_ref: str = Field(min_length=1)
    passed: bool
    status: Literal["passed", "failed", "blocked"]
    message: str = Field(min_length=1)
    created_at: datetime
