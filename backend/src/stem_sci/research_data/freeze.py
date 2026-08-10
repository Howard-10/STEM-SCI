"""Deterministic CSV data freezing and integrity checks for the MVP."""

from __future__ import annotations

import csv
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

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
        schema = self._schema_from_csv(source)
        content = source.read_bytes()
        destination_directory.mkdir(parents=True, exist_ok=True)
        frozen_path = destination_directory / f"{processed_dataset.dataset_id}-v{processed_dataset.version}.csv"
        shutil.copyfile(source, frozen_path)
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
            created_at=now,
            source_dataset_ref=processed_dataset.ref,
            freeze_approval_ref=freeze_approval_ref,
            schema_ref=f"schema://csv/{sha256_text('|'.join(schema))}",
            frozen_at=now,
        )

    def assert_integrity(self, dataset: FrozenDatasetRef) -> None:
        path = Path(dataset.content_uri)
        if not path.is_file():
            raise FrozenDatasetIntegrityError("frozen dataset file is unavailable")
        actual_hash = sha256_bytes(path.read_bytes())
        if actual_hash != dataset.sha256:
            raise FrozenDatasetIntegrityError("frozen dataset SHA256 does not match")

    @staticmethod
    def _schema_from_csv(path: Path) -> tuple[str, ...]:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.reader(source)
            header = next(reader, None)
        if not header or any(not value.strip() for value in header):
            raise ValueError("CSV requires a non-empty header")
        return tuple(header)
