"""Synthetic, non-human CSV fixture for the PYTHON_ONLY acceptance demo."""

from __future__ import annotations

import csv
from pathlib import Path


SYNTHETIC_DEMO_COLUMNS = (
    "participant_id",
    "group",
    "time",
    "baseline_score",
    "physics_modeling_score",
    "transfer_score",
    "prompt_dependency",
)

SYNTHETIC_DEMO_ROWS = (
    ("seed-001", "ai_scaffold", "post", 51, 76, 78, 2),
    ("seed-002", "ai_scaffold", "post", 48, 73, 74, 3),
    ("seed-003", "ai_scaffold", "post", 54, 79, 81, 2),
    ("seed-004", "static_prompt", "post", 50, 65, 62, 5),
    ("seed-005", "static_prompt", "post", 52, 67, 64, 5),
    ("seed-006", "static_prompt", "post", 49, 63, 61, 6),
)


def write_synthetic_demo_seed(path: Path) -> Path:
    """Write a reproducible CSV that contains no real participant data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(SYNTHETIC_DEMO_COLUMNS)
        writer.writerows(SYNTHETIC_DEMO_ROWS)
    return path
