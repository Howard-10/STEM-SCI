"""Append-only task and progress ledger contracts."""

from __future__ import annotations

from pydantic import Field

from .models import DomainModel


class LedgerEntry(DomainModel):
    entry_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


def append_ledger_entry(entries: list[LedgerEntry], entry: LedgerEntry) -> list[LedgerEntry]:
    if any(existing.entry_id == entry.entry_id for existing in entries):
        return list(entries)
    return [*entries, entry]
