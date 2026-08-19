from pathlib import Path

from stem_sci.agents.evidence_pipeline.models import BoundedEvidenceSynthesis
from stem_sci.context.models import EvidenceSearchRequest, SourceLocation, VerificationStatus
from stem_sci.context.service import ContextService
from stem_sci.tools import ToolRunStatus
from stem_sci.tools.builtin.evidence import (
    BoundedSynthesisValidatorTool,
    KnowledgeBaseSearchTool,
    SourceVerificationCheckerTool,
    citation_deduplicator,
)


def _service(tmp_path: Path) -> ContextService:
    service = ContextService(tmp_path)
    service.import_bytes("project-a", "a.md", b"STEM_SCI_DEMO_SEED: true\nPhysics evidence")
    service.import_bytes("project-b", "b.md", b"STEM_SCI_DEMO_SEED: true\nPhysics evidence")
    return service


def test_knowledge_base_search_is_project_scoped(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = KnowledgeBaseSearchTool(service).execute("project-a", "physics", 10)
    assert all(item.project_id == "project-a" for item in result.items)


def test_source_verification_checker_rejects_unverified_ref(tmp_path: Path) -> None:
    service = _service(tmp_path)
    ref = service.search(EvidenceSearchRequest(project_id="project-a", query="physics"))[0].evidence

    result = SourceVerificationCheckerTool(service).execute("project-a", [ref])
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "UNVERIFIED_EVIDENCE"


def test_evidence_tools_preserve_references_and_corpus_limit(tmp_path: Path) -> None:
    service = _service(tmp_path)
    ref = service.search(EvidenceSearchRequest(project_id="project-a", query="physics"))[0].evidence
    verified = service.verify_source("project-a", ref.evidence_id, "tester", "checked")
    duplicate = verified.model_copy()
    deduped = citation_deduplicator.execute("project-a", [verified, duplicate])
    assert [item.evidence_id for item in deduped] == [verified.evidence_id]

    synthesis = BoundedEvidenceSynthesis(
        synthesis_id="s1",
        project_id="project-a",
        summary="The bounded corpus reports evidence.",
        evidence_refs=[verified.evidence_id],
        corpus_limit="Only the imported project corpus was used.",
    )
    report = BoundedSynthesisValidatorTool(service).execute("project-a", synthesis)
    assert report.status is ToolRunStatus.SUCCEEDED
    assert report.approved


def test_citation_deduplicator_rejects_cross_project_ref() -> None:
    from stem_sci.context.models import EvidenceRef

    ref = EvidenceRef(
        evidence_id="e1",
        project_id="project-b",
        source_id="s1",
        chunk_id="c1",
        excerpt="x",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=1),
        verification_status=VerificationStatus.SOURCE_VERIFIED,
    )
    result = citation_deduplicator.execute("project-a", [ref])
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"
