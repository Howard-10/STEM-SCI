"""Golden evaluation dataset integrity."""

import json
from pathlib import Path


def test_context_memory_evaluation_has_thirty_unique_cases() -> None:
    path = Path(__file__).parents[1] / "evals" / "context_memory_goldens.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert all(case["expected"] for case in cases)
