from datetime import UTC, datetime

import pytest

from stem_sci.research_data import FrozenDatasetRef, ProcessedDatasetRef, RawDatasetRef


def test_dataset_versions_are_positive_and_frozen_requires_source() -> None:
    raw = RawDatasetRef(
        dataset_id="raw-1", project_id="dataset-demo", version=1,
        content_uri="dataset://raw-1/1", sha256="a" * 64, created_at=datetime.now(UTC)
    )
    processed = ProcessedDatasetRef(
        dataset_id="processed-1", project_id="dataset-demo", version=1,
        content_uri="dataset://processed-1/1", sha256="b" * 64,
        created_at=datetime.now(UTC), source_dataset_ref=raw.ref,
        processing_plan_ref="processing-plan://1", processing_approval_ref="approval://processing/1",
        processed_at=datetime.now(UTC)
    )
    frozen = FrozenDatasetRef(
        dataset_id="frozen-1", project_id="dataset-demo", version=1,
        content_uri="dataset://frozen-1/1", sha256="c" * 64,
        created_at=datetime.now(UTC), source_dataset_ref=processed.ref,
        freeze_approval_ref="approval-1", schema_ref="schema://frozen-1/v1",
        frozen_at=datetime.now(UTC)
    )
    assert frozen.source_dataset_ref == processed.ref
    with pytest.raises(ValueError):
        RawDatasetRef(
            dataset_id="invalid", project_id="dataset-demo", version=0,
            content_uri="dataset://invalid/0", sha256="d" * 64, created_at=datetime.now(UTC)
        )
