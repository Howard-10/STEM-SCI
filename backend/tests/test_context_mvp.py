"""Executable acceptance tests for the project-scoped Context MVP."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from stem_sci import api
from stem_sci.context.models import ContextBuildRequest, EvidenceSearchRequest, VerificationStatus
from stem_sci.context.service import ContextService

PROJECT_A = "project-alpha"
PROJECT_B = "project-beta"
DEMO_MARKDOWN = b"STEM_SCI_DEMO_SEED: true\n# Demo\nPython modelling evidence for STEM learning."


def text_pdf(content: str) -> bytes:
    """Build a small real PDF with extractable text for ingestion tests."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 100 Td ({content}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api, "service", ContextService(tmp_path, chunk_size=30))
    return TestClient(api.app)


def import_file(client: TestClient, project_id: str, name: str, content: bytes) -> dict[str, object]:
    response = client.post(
        "/api/v1/sources/import",
        data={"project_id": project_id},
        files={"file": (name, content)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_import_deduplication_and_source_traceability(tmp_path: Path) -> None:
    service = ContextService(tmp_path, chunk_size=30)
    source = service.import_bytes(PROJECT_A, "demo.md", DEMO_MARKDOWN)
    duplicate = service.import_bytes(PROJECT_A, "again.md", DEMO_MARKDOWN)
    assert source.verification_status is VerificationStatus.DEMO_SEED
    assert duplicate.source_id == source.source_id
    result = service.search(
        EvidenceSearchRequest(
            project_id=PROJECT_A,
            query="Python modelling",
            allowed_verification_statuses=[VerificationStatus.DEMO_SEED],
        )
    )[0]
    source_chunks = service.chunks(PROJECT_A, source.source_id)
    assert result.evidence.chunk_id in {chunk.chunk_id for chunk in source_chunks}


def test_text_pdf_import_is_chunked_and_searchable(tmp_path: Path) -> None:
    service = ContextService(tmp_path)
    pdf = text_pdf("STEM_SCI_DEMO_SEED: true PDF Python modelling evidence")
    source = service.import_bytes(PROJECT_A, "evidence.pdf", pdf)
    matches = service.search(EvidenceSearchRequest(project_id=PROJECT_A, query="Python"))
    assert source.media_type == "application/pdf"
    assert source.verification_status is VerificationStatus.DEMO_SEED
    assert matches[0].evidence.source_id == source.source_id


def test_bundle_prefers_verified_evidence_and_limits_source_chunks(tmp_path: Path) -> None:
    service = ContextService(tmp_path, chunk_size=20)
    first = service.import_bytes(
        PROJECT_A,
        "first.md",
        b"STEM_SCI_DEMO_SEED: true\n# First\nPython Python Python Python Python Python.",
    )
    second = service.import_bytes(
        PROJECT_A,
        "second.md",
        b"STEM_SCI_DEMO_SEED: true\n# Second\nPython evidence from another source.",
    )
    first_evidence = service.search(
        EvidenceSearchRequest(project_id=PROJECT_A, query="Python")
    )[0].evidence
    service.verify_source(PROJECT_A, first_evidence.evidence_id, "reviewer", "checked")
    bundle = service.build(
        ContextBuildRequest(
            project_id=PROJECT_A,
            task_ref="task-1",
            query="Python",
            token_budget=100,
            allowed_verification_statuses=[
                VerificationStatus.DEMO_SEED,
                VerificationStatus.SOURCE_VERIFIED,
            ],
        )
    )
    assert bundle.evidence_refs[0].source_id == first.source_id
    assert len([ref for ref in bundle.evidence_refs if ref.source_id == first.source_id]) == 1
    assert second.source_id in bundle.source_refs
    assert service.get_bundle(PROJECT_A, bundle.context_id).context_hash == bundle.context_hash


@pytest.mark.parametrize(
    ("filename", "content", "expected_code"),
    [
        pytest.param("bad.doc", b"not supported", "unsupported_file_type", id="unsupported-extension"),
        pytest.param("empty.txt", b"", "empty_file", id="empty-file"),
        pytest.param("large.txt", b"x" * 2_000_001, "file_too_large", id="oversized-file"),
        pytest.param("invalid.txt", b"\xff\xfe", "invalid_utf8", id="invalid-utf8"),
        pytest.param("invalid.json", b"{not valid json", "invalid_json", id="invalid-json"),
        pytest.param("invalid.pdf", b"not a PDF", "invalid_pdf", id="invalid-pdf"),
        pytest.param("scanned.pdf", blank_pdf(), "pdf_without_extractable_text", id="pdf-without-text"),
    ],
)
def test_upload_rejects_invalid_content(
    client: TestClient,
    filename: str,
    content: bytes,
    expected_code: str,
) -> None:
    response = client.post(
        "/api/v1/sources/import",
        data={"project_id": PROJECT_A},
        files={"file": (filename, content)},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code
    assert "C:\\" not in response.text


@pytest.mark.parametrize(
    ("filename", "expected_name"),
    [
        ("../safe.md", "safe.md"),
        (r"C:\outside\windows-safe.md", "windows-safe.md"),
    ],
)
def test_upload_sanitizes_posix_and_windows_filenames(
    client: TestClient,
    filename: str,
    expected_name: str,
) -> None:
    source = import_file(client, PROJECT_A, filename, DEMO_MARKDOWN)
    assert source["filename"] == expected_name
    assert "storage_path" not in source


def test_human_verified_is_explicitly_rejected(client: TestClient) -> None:
    source = import_file(client, PROJECT_A, "demo.md", DEMO_MARKDOWN)
    search = client.post(
        "/api/v1/evidence/search",
        json={"project_id": PROJECT_A, "query": "Python"},
    )
    evidence_id = search.json()[0]["evidence"]["evidence_id"]
    response = client.post(
        f"/api/v1/evidence/{evidence_id}/verify-source",
        params={
            "project_id": PROJECT_A,
            "verified_by": "tester",
            "verification_note": "checked",
            "verification_status": "human_verified",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_verification_parameter"
    assert source["verification_status"] == "demo_seed"


def test_api_flow_records_verification_and_retrieves_chunk(client: TestClient) -> None:
    source = import_file(client, PROJECT_A, "demo.md", DEMO_MARKDOWN)
    source_id = source["source_id"]
    search = client.post(
        "/api/v1/evidence/search",
        json={"project_id": PROJECT_A, "query": "Python"},
    )
    evidence_id = search.json()[0]["evidence"]["evidence_id"]
    verified = client.post(
        f"/api/v1/evidence/{evidence_id}/verify-source",
        params={
            "project_id": PROJECT_A,
            "verified_by": "tester",
            "verification_note": "checked against source",
        },
    )
    assert verified.status_code == 200
    detail = client.get(
        f"/api/v1/evidence/{evidence_id}", params={"project_id": PROJECT_A}
    )
    assert detail.json()["verification_status"] == "source_verified"
    assert detail.json()["verified_by"] == "tester"
    chunks = client.get(f"/api/v1/sources/{source_id}/chunks", params={"project_id": PROJECT_A})
    assert chunks.status_code == 200
    assert detail.json()["chunk_id"] in {chunk["chunk_id"] for chunk in chunks.json()}
    bundle = client.post(
        "/api/v1/context/build",
        json={"project_id": PROJECT_A, "task_ref": "demo", "query": "Python", "token_budget": 100},
    )
    assert bundle.status_code == 200
    assert client.get(
        f"/api/v1/context/{bundle.json()['context_id']}",
        params={"project_id": PROJECT_A},
    ).status_code == 200


def test_project_data_isolation(client: TestClient) -> None:
    alpha = import_file(client, PROJECT_A, "alpha.md", DEMO_MARKDOWN)
    beta = import_file(client, PROJECT_B, "beta.md", DEMO_MARKDOWN)
    assert alpha["source_id"] != beta["source_id"]
    assert client.get(f"/api/v1/sources/{alpha['source_id']}", params={"project_id": PROJECT_B}).status_code == 404
    alpha_search = client.post(
        "/api/v1/evidence/search", json={"project_id": PROJECT_A, "query": "Python"}
    ).json()
    beta_search = client.post(
        "/api/v1/evidence/search", json={"project_id": PROJECT_B, "query": "Python"}
    ).json()
    assert alpha_search[0]["evidence"]["project_id"] == PROJECT_A
    assert beta_search[0]["evidence"]["project_id"] == PROJECT_B
    assert client.get(
        f"/api/v1/evidence/{alpha_search[0]['evidence']['evidence_id']}",
        params={"project_id": PROJECT_B},
    ).status_code == 404


def test_cors_preflight_allows_only_configured_local_frontend(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/evidence/search",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    rejected = client.options(
        "/api/v1/evidence/search",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in rejected.headers


def test_request_models_reject_extra_fields_and_internal_errors_are_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_request = client.post(
        "/api/v1/context/build",
        json={"project_id": PROJECT_A, "task_ref": "task", "query": "Python", "token_budget": 10, "extra": True},
    )
    assert invalid_request.status_code == 422
    assert invalid_request.json()["error"]["code"] == "invalid_request"

    class BrokenService:
        def list_sources(self, _: str) -> list[object]:
            raise RuntimeError(r"C:\Users\admin\sensitive-path")

    monkeypatch.setattr(api, "service", BrokenService())
    safe_client = TestClient(api.app, raise_server_exceptions=False)
    response = safe_client.get("/api/v1/sources", params={"project_id": PROJECT_A})
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "An internal error occurred"}}
    assert "C:\\Users" not in response.text
