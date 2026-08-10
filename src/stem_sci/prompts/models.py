"""Prompt contracts shared by context and memory components."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PromptMessageTemplate(BaseModel):
    """One role-specific message in a prompt."""

    model_config = ConfigDict(frozen=True)
    role: Literal["system", "human", "ai"]
    template: str = Field(min_length=1)


class PromptSpec(BaseModel):
    """Immutable, semantically-versioned prompt definition."""

    model_config = ConfigDict(frozen=True)
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str
    messages: tuple[PromptMessageTemplate, ...]
    max_variable_chars: int = Field(default=50_000, ge=1)

    @property
    def content_hash(self) -> str:
        material = "\n".join(
            [self.name, self.version]
            + [f"{message.role}:{message.template}" for message in self.messages]
        )
        return sha256(material.encode("utf-8")).hexdigest()


class PromptManifest(BaseModel):
    """Serializable prompt metadata for traces and cache invalidation."""

    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    description: str
    content_hash: str
    input_variables: tuple[str, ...]
