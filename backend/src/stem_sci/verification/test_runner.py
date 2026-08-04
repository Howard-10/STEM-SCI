"""Research-test execution adapter with explicit unsupported default."""

from __future__ import annotations

from datetime import UTC, datetime

from .models import ResearchTestResult


class ResearchTestRunner:
    """Return a traceable blocked result until a sandbox is approved."""

    def run(self, target_ref: str, rubric_ref: str) -> ResearchTestResult:
        return ResearchTestResult(
            test_result_id=f"test-{target_ref.rsplit('/', 1)[-1]}",
            project_id="unscoped",
            target_ref=target_ref,
            passed=False,
            status="blocked",
            message=f"Research-test provider is unavailable for rubric {rubric_ref}.",
            created_at=datetime.now(UTC),
        )
