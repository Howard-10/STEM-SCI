from pathlib import Path

import pytest

from stem_sci.artifacts.content_store import (
    ArtifactContent,
    InMemoryArtifactContentStore,
    SQLiteArtifactContentStore,
)


def test_content_store_is_project_scoped_and_versioned(tmp_path: Path) -> None:
    store = SQLiteArtifactContentStore(tmp_path / "workflow.db")
    first = ArtifactContent(
        project_id="physics-demo",
        artifact_id="paper-card-1",
        version=1,
        artifact_type="PaperCard",
        schema_version="v1",
        body={"title": "A"},
    )
    second = ArtifactContent(
        project_id="physics-demo",
        artifact_id="paper-card-1",
        version=2,
        artifact_type="PaperCard",
        schema_version="v1",
        body={"title": "B"},
    )

    store.put(first)
    store.put(second)

    assert store.get("physics-demo", "paper-card-1", 1) == first
    assert store.get("physics-demo", "paper-card-1") == second
    assert store.get("other-project", "paper-card-1", 1) is None
    assert store.list_versions("physics-demo", "paper-card-1") == [first, second]


def test_content_hash_is_canonical_and_rejects_tampering() -> None:
    content = ArtifactContent(
        project_id="physics-demo",
        artifact_id="matrix-1",
        version=1,
        artifact_type="EvidenceMatrixCandidate",
        schema_version="v1",
        body={"b": 2, "a": 1},
    )
    reordered = content.model_copy(update={"body": {"a": 1, "b": 2}})

    assert content.content_hash == reordered.content_hash
    with pytest.raises(ValueError, match="content_hash"):
        ArtifactContent(
            project_id="physics-demo",
            artifact_id="matrix-1",
            version=1,
            artifact_type="EvidenceMatrixCandidate",
            schema_version="v1",
            body={"a": 1},
            content_hash="0" * 64,
        )


def test_in_memory_content_store_rejects_hash_changed_after_copy() -> None:
    store = InMemoryArtifactContentStore()
    content = ArtifactContent(
        project_id="physics-demo",
        artifact_id="gap-1",
        version=1,
        artifact_type="ResearchGapReport",
        schema_version="v1",
        body={"gap": "bounded"},
    )
    tampered = content.model_copy(update={"body": {"gap": "changed"}})

    with pytest.raises(ValueError, match="content_hash"):
        store.put(tampered)
