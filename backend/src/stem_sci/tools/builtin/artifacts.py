"""Project-scoped artifact content resolution and integrity checks."""

from __future__ import annotations

from typing import Any

from stem_sci.artifacts.content_store import ArtifactContent, ArtifactContentStore
from stem_sci.tools.models import ToolRunStatus
from stem_sci.tools.policies import ToolPolicyError

from .common import BuiltinResult, blocked, execute_wrapped, failed, project_ref


class ArtifactResolveTool:
    tool_id = "artifact_resolve"

    def __init__(self, content_store: ArtifactContentStore) -> None:
        self.content_store = content_store

    def execute(self, project_id: str, artifact_ref: str) -> BuiltinResult[Any]:
        def resolve() -> ArtifactContent:
            parts = project_ref(project_id, artifact_ref)
            if len(parts) != 2:
                raise ToolPolicyError("REFERENCE_INVALID")
            artifact_id, version = parts
            try:
                parsed_version = int(version)
            except ValueError as error:
                raise ToolPolicyError("REFERENCE_INVALID") from error
            item = self.content_store.get(project_id, artifact_id, parsed_version)
            if item is None:
                raise LookupError(artifact_ref)
            return item

        return execute_wrapped(resolve)


class ArtifactIntegrityCheckTool:
    tool_id = "artifact_integrity_check"

    def __init__(self, content_store: ArtifactContentStore) -> None:
        self.content_store = content_store

    def execute(self, project_id: str, artifact_ref: str) -> bool | BuiltinResult[None]:
        resolved = ArtifactResolveTool(self.content_store).execute(project_id, artifact_ref)
        if isinstance(resolved, BuiltinResult):
            if resolved.status is not ToolRunStatus.SUCCEEDED:
                return resolved
            content = resolved.value
        else:
            content = resolved
        try:
            if content is None:
                return failed("REFERENCE_NOT_FOUND")
            content.validate_integrity()
        except ValueError:
            return blocked("HASH_MISMATCH")
        return True


artifact_resolve: ArtifactResolveTool | None = None
artifact_integrity_check: ArtifactIntegrityCheckTool | None = None

__all__ = ["ArtifactIntegrityCheckTool", "ArtifactResolveTool", "artifact_integrity_check", "artifact_resolve"]
