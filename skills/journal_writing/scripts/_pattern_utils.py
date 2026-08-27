"""Shared paths and YAML helpers for the journal-writing skill."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]


def exemplar_root() -> Path:
    """Return the existing exemplar root without renaming legacy content."""

    for name in ("exemplars", "examplars"):
        candidate = SKILL_ROOT / name
        if candidate.is_dir():
            return candidate
    return SKILL_ROOT / "exemplars"


def journal_dir(journal: str) -> Path:
    return exemplar_root() / journal


def paper_files(journal: str) -> list[Path]:
    base = journal_dir(journal)
    papers = base / "papers"
    search_root = papers if papers.is_dir() else base
    return sorted(search_root.glob("*.pdf"), key=lambda path: path.name.casefold())


def cards_dir(journal: str, *, create: bool = False) -> Path:
    path = journal_dir(journal) / "cards"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def card_files(journal: str | None = None) -> list[Path]:
    if journal:
        return sorted(cards_dir(journal).glob("*.yaml"), key=lambda path: path.name.casefold())
    root = exemplar_root()
    return sorted(root.glob("*/cards/*.yaml"), key=lambda path: str(path).casefold())


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def dump_yaml(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        yaml.safe_dump(
            data,
            stream,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )
    temporary.replace(path)


def ordered_present_fields(mapping: dict[str, Any], field_order: Iterable[str]) -> list[str]:
    return [field for field in field_order if mapping.get(field) not in (None, [], "")]


def canonical_methodology(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    if "instrument" in normalized and any(word in normalized for word in ("develop", "validat")):
        return "instrument_development"
    if "experiment" in normalized or "randomized" in normalized or "randomised" in normalized:
        return "experiment"
    if "mixed" in normalized or "sequential_explanatory" in normalized:
        return "mixed_methods"
    if "qualitative" in normalized or "case_study" in normalized:
        return "qualitative"
    if "quantitative" in normalized or any(
        word in normalized for word in ("survey", "regression", "path_analysis", "structural_equation")
    ):
        return "quantitative"
    return None
