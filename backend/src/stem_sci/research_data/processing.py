"""Controller-invoked, approved CSV processing for the synthetic MVP."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from stem_sci.research_data.canonical import canonical_csv_bytes, read_csv_rows
from stem_sci.research_data.models import ProcessedDatasetRef, RawDatasetRef
from stem_sci.utils.hash_utils import sha256_bytes


class DataProcessingService:
    """Create a ProcessedDataset after an explicit plan and human approval.

    The MVP has no automatic cleaning rule.  Its only supported operation is a
    lossless, traceable CSV copy, which prevents an Agent from silently
    changing raw values while preserving the Raw → Processed lifecycle.
    """

    def process_csv_identity(
        self,
        *,
        raw_dataset: RawDatasetRef,
        processing_plan_ref: str,
        processing_approval_ref: str,
        destination_directory: Path,
    ) -> ProcessedDatasetRef:
        source = Path(raw_dataset.content_uri)
        if source.suffix.lower() != ".csv":
            raise ValueError("MVP data processing supports CSV only")
        if not source.is_file():
            raise ValueError("raw dataset file does not exist")
        raw_content = source.read_bytes()
        if sha256_bytes(raw_content) != raw_dataset.sha256:
            raise ValueError("raw dataset SHA256 does not match")
        fieldnames, rows = read_csv_rows(raw_content)
        content = canonical_csv_bytes(fieldnames, rows)
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = destination_directory / f"{raw_dataset.dataset_id}-v{raw_dataset.version}.csv"
        destination.write_bytes(content)
        now = datetime.now(UTC)
        return ProcessedDatasetRef(
            dataset_id=f"processed-{raw_dataset.dataset_id}",
            project_id=raw_dataset.project_id,
            version=raw_dataset.version,
            content_uri=str(destination),
            sha256=sha256_bytes(content),
            raw_bytes_sha256=sha256_bytes(content),
            canonical_content_sha256=sha256_bytes(content),
            created_at=now,
            source_dataset_ref=raw_dataset.ref,
            processing_plan_ref=processing_plan_ref,
            processing_approval_ref=processing_approval_ref,
            processed_at=now,
        )
