"""Reproducible synthetic long-format fixture for the v1.0 acceptance demo."""

from __future__ import annotations

import random
from pathlib import Path

from stem_sci.research_data.canonical import canonical_csv_bytes
from stem_sci.research_data.models import SyntheticDatasetGenerationManifest
from stem_sci.utils.hash_utils import sha256_bytes


SYNTHETIC_DEMO_COLUMNS = (
    "participant_id",
    "group",
    "task_sequence",
    "task_id",
    "analysis_role",
    "measurement_period",
    "baseline_score",
    "physics_modeling_score",
    "transfer_score",
    "prompt_dependency_q1",
    "prompt_dependency_q2",
    "prompt_dependency_q3",
    "prompt_dependency_q4",
    "prompt_dependency_q5",
    "prompt_dependency_q6",
)
SYNTHETIC_DEMO_SEED = 20260812


def synthetic_demo_rows(seed: int = SYNTHETIC_DEMO_SEED) -> list[dict[str, object]]:
    """Generate 48 fake records only; no real participant data is used."""

    randomizer = random.Random(seed)
    rows: list[dict[str, object]] = []
    for index in range(48):
        group = "ai_scaffold" if index < 24 else "static_prompt"
        sequence = "AB" if index % 2 == 0 else "BA"
        baseline = round(55 + randomizer.gauss(0, 7), 3)
        participant_intercept = randomizer.gauss(0, 5.0)
        group_effect = 6.0 if group == "ai_scaffold" else 0.0
        dependency_base = 2.4 if group == "ai_scaffold" else 3.3
        dependency_intercept = randomizer.gauss(0, 0.45)
        ordered_tasks = ("A", "B") if sequence == "AB" else ("B", "A")
        for period_index, task in enumerate(ordered_tasks, start=1):
            score = (
                baseline * 0.45
                + 35
                + group_effect
                + (period_index - 1) * 2
                + participant_intercept
                + randomizer.gauss(0, 1.2)
            )
            dependency = (
                dependency_base
                + (period_index - 1) * -0.15
                + dependency_intercept
                + randomizer.gauss(0, 0.35)
            )
            rows.append(
                {
                    "participant_id": f"seed-{index + 1:03d}",
                    "group": group,
                    "task_sequence": sequence,
                    "task_id": task,
                    "analysis_role": "repeated_modeling",
                    "measurement_period": f"period{period_index}",
                    "baseline_score": baseline,
                    "physics_modeling_score": round(score, 3),
                    "transfer_score": "",
                    **_dependency_items(dependency),
                }
            )
        transfer = baseline * 0.40 + 38 + group_effect * 0.8 + participant_intercept + randomizer.gauss(0, 3)
        rows.append(
            {
                "participant_id": f"seed-{index + 1:03d}",
                "group": group,
                "task_sequence": sequence,
                "task_id": "C",
                "analysis_role": "transfer",
                "measurement_period": "",
                "baseline_score": baseline,
                "physics_modeling_score": "",
                "transfer_score": round(transfer, 3),
                **{f"prompt_dependency_q{item}": "" for item in range(1, 7)},
            }
        )
    return rows


# Compatibility fixture for the pre-v1 API tests. New code uses the full
# synthetic long table and ``SyntheticDatasetGenerationManifest`` instead.
def synthetic_demo_manifest(seed: int = SYNTHETIC_DEMO_SEED) -> SyntheticDatasetGenerationManifest:
    content = canonical_csv_bytes(SYNTHETIC_DEMO_COLUMNS, synthetic_demo_rows(seed))
    return SyntheticDatasetGenerationManifest(
        manifest_id=f"synthetic-demo-{seed}",
        random_seed=seed,
        participant_count=48,
        group_allocation_rule="First 24 ai_scaffold, remaining 24 static_prompt.",
        sequence_allocation_rule="AB/BA alternating within each group, 12 per group-sequence cell.",
        effect_parameters={"modeling_group_effect": 6.0, "transfer_group_effect": 4.8},
        noise_parameters={"baseline_sd": 7.0, "outcome_sd": 3.0},
        missingness_parameters={"rate": 0.0},
        generated_dataset_sha256=sha256_bytes(content),
    )


def write_synthetic_demo_seed(path: Path, seed: int = SYNTHETIC_DEMO_SEED) -> Path:
    """Write canonical LF UTF-8 demo data and return its path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_csv_bytes(SYNTHETIC_DEMO_COLUMNS, synthetic_demo_rows(seed)))
    return path


def _dependency_items(mean: float) -> dict[str, int]:
    return {
        f"prompt_dependency_q{item}": max(
            1, min(5, round(mean + ((item - 3.5) * 0.18)))
        )
        for item in range(1, 7)
    }


SYNTHETIC_DEMO_ROWS = tuple(
    tuple(str(row[column]) for column in SYNTHETIC_DEMO_COLUMNS)
    for row in synthetic_demo_rows()
    if row["task_id"] == "C"
)
