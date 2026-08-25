"""Canonical CSV serialization used for stable dataset-content hashes."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping, Sequence

from .models import AnalysisDatasetSerializationPolicy
from stem_sci.utils.hash_utils import sha256_bytes


def canonical_csv_bytes(
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
    *,
    policy: AnalysisDatasetSerializationPolicy | None = None,
) -> bytes:
    """Serialize CSV data deterministically, independent of host line endings."""

    active_policy = policy or AnalysisDatasetSerializationPolicy()
    ordered_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: tuple(_sort_value(row.get(column)) for column in active_policy.row_order),
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in ordered_rows:
        writer.writerow({column: _cell(row.get(column)) for column in fieldnames})
    return output.getvalue().encode("utf-8")


def canonical_csv_hash(
    fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> str:
    return sha256_bytes(canonical_csv_bytes(fieldnames, rows))


def read_csv_rows(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Decode a UTF-8 CSV once before applying canonical hashing or validation."""

    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("CSV requires a non-empty header")
    fieldnames = list(reader.fieldnames)
    if not fieldnames or any(not value.strip() for value in fieldnames):
        raise ValueError("CSV requires a non-empty header")
    return fieldnames, [dict(row) for row in reader]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".17g")
    return str(value)


def _sort_value(value: object) -> tuple[int, str]:
    if value is None:
        return (0, "")
    return (1, _cell(value))
