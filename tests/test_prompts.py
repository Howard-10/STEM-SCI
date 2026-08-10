"""Prompt registry invariants."""

import pytest

from stem_sci.prompts.defaults import create_default_registry
from stem_sci.prompts.models import PromptMessageTemplate, PromptSpec
from stem_sci.prompts.registry import PromptRegistryError


def test_prompt_rendering_is_role_aware_and_strict() -> None:
    registry = create_default_registry()
    messages = registry.render(
        "context.base",
        "1.0.0",
        {
            "task": "Assess feasibility",
            "forbidden_operations": "Invent data",
            "output_requirements": "JSON",
        },
    )
    assert messages[0].type == "system"
    assert "Assess feasibility" in messages[0].content
    with pytest.raises(PromptRegistryError, match="missing"):
        registry.render("context.base", "1.0.0", {"task": "x"})
    with pytest.raises(PromptRegistryError, match="unknown"):
        registry.render(
            "context.base",
            "1.0.0",
            {"task": "x", "forbidden_operations": "x", "output_requirements": "x", "extra": "x"},
        )


def test_prompt_manifest_hash_changes_with_content() -> None:
    registry = create_default_registry()
    original = registry.manifest("context.base", "1.0.0")
    registry.register(
        PromptSpec(
            name="context.base",
            version="1.0.1",
            description="changed",
            messages=(PromptMessageTemplate(role="system", template="Changed {task}"),),
        )
    )
    changed = registry.manifest("context.base", "1.0.1")
    assert original.content_hash != changed.content_hash
    assert changed.input_variables == ("task",)
