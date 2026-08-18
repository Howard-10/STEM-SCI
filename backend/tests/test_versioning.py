from datetime import UTC, datetime

import pytest

from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.models import ArtifactRef


def test_artifact_versions_are_positive_and_latest_lookup_is_versioned() -> None:
    store = InMemoryArtifactStore()
    for version in (1, 2):
        store.put(ArtifactRef(
            artifact_id="protocol", project_id="version-demo", artifact_type="StudyProtocol",
            version=version, content_uri=f"artifact://protocol/{version}", sha256=("a" if version == 1 else "b") * 64,
            created_at=datetime.now(UTC), created_by="research_design"
        ))
    assert store.get("version-demo", "protocol").version == 2
    assert [item.version for item in store.list_versions("version-demo", "protocol")] == [1, 2]
    with pytest.raises(ValueError):
        ArtifactRef(
            artifact_id="invalid", project_id="version-demo", artifact_type="x", version=0,
            content_uri="artifact://invalid/0", sha256="a" * 64,
            created_at=datetime.now(UTC), created_by="test"
        )
