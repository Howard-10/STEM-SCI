"""Validated prompt registration and rendering."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any

from stem_sci.compat.langchain import BaseMessage, ChatPromptTemplate

from .models import PromptManifest, PromptSpec


class PromptRegistryError(ValueError):
    """Raised for duplicate, missing, or invalid prompt operations."""


class PromptRegistry:
    """Thread-safe registry keyed by prompt name and semantic version."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], PromptSpec] = {}
        self._templates: dict[tuple[str, str], ChatPromptTemplate] = {}
        self._lock = RLock()

    def register(self, spec: PromptSpec) -> None:
        key = (spec.name, spec.version)
        template = ChatPromptTemplate.from_messages(
            [(message.role, message.template) for message in spec.messages]
        )
        with self._lock:
            if key in self._specs:
                raise PromptRegistryError(f"Prompt already registered: {spec.name}@{spec.version}")
            self._specs[key] = spec
            self._templates[key] = template

    def render(self, name: str, version: str, variables: Mapping[str, Any]) -> list[BaseMessage]:
        key = (name, version)
        with self._lock:
            spec = self._require(key)
            template = self._templates[key]
        required = set(template.input_variables)
        supplied = set(variables)
        missing, unknown = required - supplied, supplied - required
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing={sorted(missing)}")
            if unknown:
                details.append(f"unknown={sorted(unknown)}")
            raise PromptRegistryError("Invalid prompt variables: " + ", ".join(details))
        for variable, value in variables.items():
            if not isinstance(value, (str, int, float, bool)):
                raise PromptRegistryError(
                    f"Prompt variable {variable!r} must be a scalar, got {type(value).__name__}"
                )
            if len(str(value)) > spec.max_variable_chars:
                raise PromptRegistryError(
                    f"Prompt variable {variable!r} exceeds {spec.max_variable_chars} characters"
                )
        return list(template.invoke(dict(variables)).to_messages())

    def manifest(self, name: str, version: str) -> PromptManifest:
        key = (name, version)
        with self._lock:
            spec = self._require(key)
            variables = tuple(sorted(self._templates[key].input_variables))
        return PromptManifest(
            name=spec.name,
            version=spec.version,
            description=spec.description,
            content_hash=spec.content_hash,
            input_variables=variables,
        )

    def _require(self, key: tuple[str, str]) -> PromptSpec:
        try:
            return self._specs[key]
        except KeyError as exc:
            raise PromptRegistryError(f"Unknown prompt: {key[0]}@{key[1]}") from exc


_DEFAULT_REGISTRY: PromptRegistry | None = None


def _default_registry() -> PromptRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from .defaults import create_default_registry

        _DEFAULT_REGISTRY = create_default_registry()
    return _DEFAULT_REGISTRY


def render_prompt(name: str, version: str, variables: Mapping[str, Any]) -> list[BaseMessage]:
    return _default_registry().render(name, version, variables)


def get_prompt_manifest(name: str, version: str) -> PromptManifest:
    return _default_registry().manifest(name, version)
