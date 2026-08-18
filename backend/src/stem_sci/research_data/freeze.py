"""Deterministic CSV data freezing and integrity checks for the MVP."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from stem_sci.research_data.canonical import canonical_csv_bytes, read_csv_rows
from stem_sci.research_data.models import FrozenDatasetRef, ProcessedDatasetRef
from stem_sci.utils.hash_utils import sha256_bytes, sha256_text


class FrozenDatasetIntegrityError(ValueError):
    """Raised when a FrozenDataset no longer matches its recorded SHA256."""


class DataFreezeService:
    """Controller-invoked service that copies and freezes an approved CSV.

    The service accepts only an already-created ``ProcessedDatasetRef`` and a
    human approval reference.  It does not infer processing decisions or alter
    source records.
    """

    def freeze_csv(
        self,
        *,
        processed_dataset: ProcessedDatasetRef,
        freeze_approval_ref: str,
        destination_directory: Path,
    ) -> FrozenDatasetRef:
        source = Path(processed_dataset.content_uri)
        if source.suffix.lower() != ".csv":
            raise ValueError("MVP data freezing supports CSV only")
        if not source.is_file():
            raise ValueError("processed dataset file does not exist")
        fieldnames, rows = read_csv_rows(source.read_bytes())
        content = canonical_csv_bytes(fieldnames, rows)
        destination_directory.mkdir(parents=True, exist_ok=True)
        frozen_path = destination_directory / f"{processed_dataset.dataset_id}-v{processed_dataset.version}.csv"
        frozen_path.write_bytes(content)
        # Best-effort local protection.  Integrity is always enforced via the
        # recorded hash, including on platforms where ACLs are unavailable.
        os.chmod(frozen_path, 0o444)
        now = datetime.now(UTC)
        return FrozenDatasetRef(
            dataset_id=f"frozen-{processed_dataset.dataset_id}",
            project_id=processed_dataset.project_id,
            version=processed_dataset.version,
            content_uri=str(frozen_path),
            sha256=sha256_bytes(content),
            raw_bytes_sha256=sha256_bytes(content),
            canonical_content_sha256=sha256_bytes(content),
            created_at=now,
            source_dataset_ref=processed_dataset.ref,
            freeze_approval_ref=freeze_approval_ref,
            schema_ref=f"schema://csv/{sha256_text('|'.join(fieldnames))}",
            frozen_at=now,
        )

    def assert_integrity(self, dataset: FrozenDatasetRef) -> None:
        path = Path(dataset.content_uri)
        if not path.is_file():
            raise FrozenDatasetIntegrityError("frozen dataset file is unavailable")
        content = path.read_bytes()
        actual_hash = sha256_bytes(content)
        if actual_hash != dataset.raw_bytes_sha256 or actual_hash != dataset.sha256:
            raise FrozenDatasetIntegrityError("frozen dataset byte SHA256 does not match")
        fieldnames, rows = read_csv_rows(content)
        canonical_hash = sha256_bytes(canonical_csv_bytes(fieldnames, rows))
        if canonical_hash != dataset.canonical_content_sha256:
            raise FrozenDatasetIntegrityError("frozen dataset canonical SHA256 does not match")
