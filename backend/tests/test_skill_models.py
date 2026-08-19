import pytest
from pydantic import ValidationError

from stem_sci.skills.models import RiskLevel, SkillManifest


def _manifest(**overrides: object) -> SkillManifest:
    values: dict[str, object] = {
        "skill_id": "bounded_corpus_review",
        "skill_version": "v1",
        "agent_ids": ["evidence_review"],
        "supported_task_types": ["synthesize_evidence"],
        "required_tool_ids": ["context_bundle_read"],
        "input_schema_refs": ["schema://EvidenceReviewContext"],
        "output_schema_refs": ["schema://BoundedEvidenceSynthesis"],
        "prompt_template_refs": ["prompt://evidence-review-v1"],
        "validator_refs": ["validator://evidence"],
        "risk_level": RiskLevel.MEDIUM,
    }
    values.update(overrides)
    return SkillManifest(**values)


def test_skill_manifest_requires_tool_binding() -> None:
    with pytest.raises(ValidationError):
        _manifest(required_tool_ids=[])


def test_skill_manifest_rejects_invalid_risk_level_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _manifest(risk_level="critical")
    with pytest.raises(ValidationError):
        _manifest(unexpected="value")


def test_skill_manifest_preserves_versioned_bindings() -> None:
    manifest = _manifest()

    assert manifest.skill_id == "bounded_corpus_review"
    assert manifest.skill_version == "v1"
    assert manifest.risk_level is RiskLevel.MEDIUM
    assert manifest.required_tool_ids == ["context_bundle_read"]
