"""Resolve an explicitly allowed Skill for one Agent task."""

from __future__ import annotations

from stem_sci.tools.registry import ToolRegistry

from .models import SkillManifest
from .registry import SkillRegistry


def _parse_ref(reference: str, kind: str) -> tuple[str, str]:
    identifier, separator, version = reference.partition("@")
    if not separator or not identifier or not version or "@" in version:
        raise ValueError(f"invalid {kind} reference {reference!r}; expected id@version")
    return identifier, version


class SkillResolver:
    """Apply Agent/task allow-lists and validate every Skill Tool binding."""

    def __init__(self, skill_registry: SkillRegistry, tool_registry: ToolRegistry) -> None:
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry

    def resolve_for_agent(
        self, agent_id: str, task_type: str, allowed_skill_refs: list[str]
    ) -> SkillManifest:
        if not allowed_skill_refs:
            raise ValueError("no allowed skill reference supplied")

        manifests: list[SkillManifest] = []
        for reference in allowed_skill_refs:
            skill_id, skill_version = _parse_ref(reference, "skill")
            try:
                manifest = self.skill_registry.get(skill_id, skill_version)
            except KeyError as exc:
                raise ValueError(f"unknown skill {skill_id}@{skill_version}") from exc
            if agent_id in manifest.agent_ids and task_type in manifest.supported_task_types:
                manifests.append(manifest)

        if not manifests:
            raise ValueError(
                f"no allowed skill matches agent {agent_id} and task {task_type}"
            )
        if len(manifests) > 1:
            refs = ", ".join(
                f"{manifest.skill_id}@{manifest.skill_version}" for manifest in manifests
            )
            raise ValueError(f"multiple allowed skills match agent/task: {refs}")
        manifest = manifests[0]

        for tool_ref in manifest.required_tool_ids:
            tool_id, tool_version = (
                _parse_ref(tool_ref, "tool") if "@" in tool_ref else (tool_ref, None)
            )
            try:
                self.tool_registry.get(tool_id, tool_version)
            except KeyError as exc:
                raise ValueError(
                    f"tool not registered: {tool_ref} required by skill "
                    f"{manifest.skill_id}@{manifest.skill_version}"
                ) from exc
            except ValueError as exc:
                raise ValueError(
                    f"tool version is ambiguous: {tool_id} required by skill "
                    f"{manifest.skill_id}@{manifest.skill_version}"
                ) from exc
        return manifest
