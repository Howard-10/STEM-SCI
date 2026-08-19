"""Deterministic, version-aware registry for Skill manifests."""

from __future__ import annotations

from collections.abc import Iterable

from .models import SkillManifest


class SkillRegistry:
    """In-memory registry keyed by the stable ``skill_id@skill_version`` pair."""

    def __init__(self, manifests: Iterable[SkillManifest] = ()) -> None:
        self._manifests: dict[tuple[str, str], SkillManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: SkillManifest) -> None:
        key = (manifest.skill_id, manifest.skill_version)
        if key in self._manifests:
            raise ValueError(
                f"skill {manifest.skill_id}@{manifest.skill_version} is already registered"
            )
        self._manifests[key] = manifest

    def get(self, skill_id: str, skill_version: str | None = None) -> SkillManifest:
        if skill_version is not None:
            try:
                return self._manifests[(skill_id, skill_version)]
            except KeyError as exc:
                raise KeyError(f"unknown skill {skill_id}@{skill_version}") from exc

        matches = [manifest for (identifier, _), manifest in self._manifests.items() if identifier == skill_id]
        if not matches:
            raise KeyError(f"unknown skill {skill_id}")
        if len(matches) > 1:
            raise ValueError(f"skill {skill_id} has multiple versions; version is required")
        return matches[0]

    def list_for_agent(self, agent_id: str, task_type: str) -> list[SkillManifest]:
        """List manifests applicable to both an Agent role and a task type."""
        return sorted(
            (
                manifest
                for manifest in self._manifests.values()
                if agent_id in manifest.agent_ids and task_type in manifest.supported_task_types
            ),
            key=lambda manifest: (manifest.skill_id, manifest.skill_version),
        )

    def list(self) -> list[SkillManifest]:
        """Return every registered Skill in stable identifier/version order."""
        return sorted(
            self._manifests.values(), key=lambda manifest: (manifest.skill_id, manifest.skill_version)
        )

