from __future__ import annotations

import pytest

from stem_sci.tools import ToolExecutionMode, ToolSpec
from stem_sci.tools.registry import ToolRegistry


def tool_spec(tool_id: str, version: str = "v1", capability: str | None = None) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        tool_version=version,
        capability=capability or tool_id,
        execution_mode=ToolExecutionMode.READ_ONLY,
        input_schema_ref="schema://Input",
        output_schema_ref="schema://Output",
        timeout_seconds=10,
    )


def test_tool_registry_rejects_duplicate_version() -> None:
    registry = ToolRegistry([tool_spec("context_bundle_read", "v1")])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool_spec("context_bundle_read", "v1"))


def test_tool_registry_get_and_list_are_versioned_and_deterministic() -> None:
    registry = ToolRegistry(
        [
            tool_spec("zeta", "v2", "shared"),
            tool_spec("alpha", "v1", "shared"),
            tool_spec("zeta", "v1", "shared"),
        ]
    )

    assert registry.get("zeta", "v1").tool_version == "v1"
    assert [spec.tool_id + "@" + spec.tool_version for spec in registry.list()] == [
        "alpha@v1",
        "zeta@v1",
        "zeta@v2",
    ]
    assert [(spec.tool_id, spec.tool_version) for spec in registry.resolve("shared")] == [
        ("alpha", "v1"),
        ("zeta", "v1"),
        ("zeta", "v2"),
    ]


def test_tool_registry_rejects_ambiguous_unversioned_lookup() -> None:
    registry = ToolRegistry([tool_spec("context", "v1"), tool_spec("context", "v2")])
    with pytest.raises(ValueError, match="version"):
        registry.get("context")


def test_tool_registry_rejects_unknown_tool() -> None:
    with pytest.raises(KeyError, match="unknown tool"):
        ToolRegistry().get("missing", "v1")
