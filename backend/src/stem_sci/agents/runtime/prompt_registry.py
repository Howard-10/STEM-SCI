"""Versioned prompt templates for agent-internal generation stages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplate(BaseModel):
    """A named, immutable prompt template version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    user_prompt_template: str = Field(min_length=1)


class PromptRegistry:
    """In-memory registry that prevents prompt versions from being overwritten."""

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}

    def register(
        self,
        *,
        name: str,
        version: str,
        system_prompt: str,
        user_prompt_template: str,
    ) -> PromptTemplate:
        key = (name, version)
        if key in self._templates:
            raise ValueError(f"prompt {name!r} version {version!r} is already registered")
        template = PromptTemplate(
            name=name,
            version=version,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
        )
        self._templates[key] = template
        return template

    def get(self, name: str, version: str) -> PromptTemplate:
        try:
            return self._templates[(name, version)]
        except KeyError:
            raise KeyError(f"prompt {name!r} version {version!r} is not registered") from None

    def render(self, name: str, version: str, **values: object) -> tuple[str, str]:
        template = self.get(name, version)
        try:
            user_prompt = template.user_prompt_template.format_map(values)
        except KeyError as error:
            raise KeyError(f"missing prompt variable: {error.args[0]}") from None
        return template.system_prompt, user_prompt
