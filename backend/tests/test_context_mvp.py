from pathlib import Path

import pytest

from stem_sci.context.models import ContextBuildRequest, EvidenceSearchRequest, VerificationStatus
from stem_sci.context.service import ContextService


def test_import_search_verify_and_bundle(tmp_path: Path) -> None:
    service = ContextService(tmp_path, chunk_size=30)
    source = service.import_bytes("demo.md", b"# Demo\nSTEM scaffolding improves Python modelling transfer.", VerificationStatus.DEMO_SEED)
    assert service.import_bytes("again.md", b"# Demo\nSTEM scaffolding improves Python modelling transfer.").source_id == source.source_id
    result = service.search(EvidenceSearchRequest(query="Python modelling", allowed_verification_statuses=[VerificationStatus.DEMO_SEED]))[0]
    verified = service.verify_source(result.evidence.evidence_id, "researcher", "checked source")
    assert verified.verification_status is VerificationStatus.SOURCE_VERIFIED
    bundle = service.build(ContextBuildRequest(task_ref="task-1", query="Python modelling", token_budget=100))
    assert bundle.evidence_refs and bundle.estimated_tokens <= bundle.token_budget
    assert service.get_bundle(bundle.context_id).context_hash == bundle.context_hash

def test_invalid_type_and_human_verification_blocked(tmp_path: Path) -> None:
    service = ContextService(tmp_path)
    with pytest.raises(ValueError): service.import_bytes("bad.pdf", b"no")


def test_api_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from stem_sci import api
    monkeypatch.setattr(api, "service", ContextService(tmp_path))
    client = TestClient(api.app)
    assert client.get("/api/v1/health").json()["status"] == "ok"
    imported = client.post("/api/v1/sources/import", files={"file": ("demo.txt", b"verified learning evidence", "text/plain")}).json()
    assert "storage_path" not in imported
    search = client.post("/api/v1/evidence/search", json={"query": "learning"}).json()[0]
    evidence_id = search["evidence"]["evidence_id"]
    assert client.post(f"/api/v1/evidence/{evidence_id}/verify-source?verified_by=tester&verification_note=checked").status_code == 200
    bundle = client.post("/api/v1/context/build", json={"task_ref": "demo", "query": "learning", "token_budget": 100}).json()
    assert client.get(f"/api/v1/context/{bundle['context_id']}").status_code == 200
