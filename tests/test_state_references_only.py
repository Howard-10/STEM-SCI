"""Reference-only state storage invariants."""

import pytest

from stem_sci.core.state import validate_reference_only_state


def test_reference_only_state_accepts_refs_and_rejects_large_objects() -> None:
    validate_reference_only_state({"evidence_refs": ["ev_1"], "artifact_refs": ["art_1"]})
    with pytest.raises(ValueError, match="Large objects"):
        validate_reference_only_state({"full_evidence": ["large payload"]})  # type: ignore[typeddict-unknown-key]
    with pytest.raises(TypeError, match="Binary"):
        validate_reference_only_state({"conversation_summary": b"binary"})  # type: ignore[typeddict-item]
