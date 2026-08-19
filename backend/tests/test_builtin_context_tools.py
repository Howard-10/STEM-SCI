from pathlib import Path

from stem_sci.artifacts.content_store import InMemoryArtifactContentStore
from stem_sci.context.models import ContextBuildRequest, EvidenceSearchRequest
from stem_sci.context.service import ContextService
from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.artifacts import ArtifactResolveTool
from stem_sci.tools.builtin.context import ContextBundleReadTool, EvidenceRefValidateTool


def _service(tmp_path: Path) -> ContextService:
    service = ContextService(tmp_path)
    service.import_bytes("project-a", "a.md", b"STEM_SCI_DEMO_SEED: true\nPhysics evidence")
    return service


def test_context_bundle_read_is_project_scoped(tmp_path: Path) -> None:
    service = _service(tmp_path)
    context = service.build(ContextBuildRequest(project_id="project-a", task_ref="task", query="Physics", token_budget=100))
    tool = ContextBundleReadTool(service)

    assert tool.execute("project-a", context.context_id).project_id == "project-a"
    blocked = tool.execute("project-b", context.context_id)
    assert blocked.status is ToolRunStatus.BLOCKED
    assert blocked.error_code == "PROJECT_SCOPE_VIOLATION"


def test_evidence_ref_validate_rejects_cross_project_reference(tmp_path: Path) -> None:
    service = _service(tmp_path)
    evidence = service.search(EvidenceSearchRequest(project_id="project-a", query="Physics"))[0].evidence
    tool = EvidenceRefValidateTool(service)

    result = tool.execute("project-b", evidence.evidence_id)
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_artifact_resolve_rejects_cross_project_reference() -> None:
    store = InMemoryArtifactContentStore()
    tool = ArtifactResolveTool(store)

    result = tool.execute("project-a", "artifact-content://project-b/a/1")
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"
