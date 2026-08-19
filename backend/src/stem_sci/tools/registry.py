"""Deterministic, version-aware registry for Controller-visible Tools."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ToolSpec


def _key(identifier: str, version: str) -> tuple[str, str]:
    return identifier, version


class ToolRegistry:
    """In-memory registry keyed by the stable ``tool_id@tool_version`` pair."""

    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[tuple[str, str], ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        key = _key(spec.tool_id, spec.tool_version)
        if key in self._specs:
            raise ValueError(f"tool {spec.tool_id}@{spec.tool_version} is already registered")
        self._specs[key] = spec

    def get(self, tool_id: str, tool_version: str | None = None) -> ToolSpec:
        if tool_version is not None:
            try:
                return self._specs[(tool_id, tool_version)]
            except KeyError as exc:
                raise KeyError(f"unknown tool {tool_id}@{tool_version}") from exc

        matches = [spec for (identifier, _), spec in self._specs.items() if identifier == tool_id]
        if not matches:
            raise KeyError(f"unknown tool {tool_id}")
        if len(matches) > 1:
            raise ValueError(f"tool {tool_id} has multiple versions; version is required")
        return matches[0]

    def resolve(self, capability: str) -> list[ToolSpec]:
        """Return all versions for a capability in stable identifier order."""
        return sorted(
            (spec for spec in self._specs.values() if spec.capability == capability),
            key=lambda spec: (spec.tool_id, spec.tool_version),
        )

    def list(self) -> list[ToolSpec]:
        """Return every registered Tool in stable identifier/version order."""
        return sorted(self._specs.values(), key=lambda spec: (spec.tool_id, spec.tool_version))

