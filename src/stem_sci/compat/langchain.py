# mypy: disable-error-code="unused-ignore,return-value"
"""Import LangChain primitives, with a minimal offline test fallback."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import Any

try:  # pragma: no cover - exercised in deployment environments
    from langchain_core.messages import (  # type: ignore[import-not-found]
        BaseMessage,
        HumanMessage,
        SystemMessage,
    )
    from langchain_core.prompts import ChatPromptTemplate  # type: ignore[import-not-found]

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback is covered through consuming modules
    LANGCHAIN_AVAILABLE = False

    @dataclass
    class BaseMessage:  # type: ignore[no-redef]
        content: Any
        id: str | None = None
        type: str = "base"

    class HumanMessage(BaseMessage):  # type: ignore[misc,no-redef]
        type = "human"

        def __init__(self, content: Any, id: str | None = None) -> None:
            super().__init__(content=content, id=id, type="human")

    class SystemMessage(BaseMessage):  # type: ignore[misc,no-redef]
        type = "system"

        def __init__(self, content: Any, id: str | None = None) -> None:
            super().__init__(content=content, id=id, type="system")

    class _PromptValue:
        def __init__(self, messages: list[BaseMessage]) -> None:
            self.messages = messages

        def to_messages(self) -> list[BaseMessage]:
            return list(self.messages)

    class ChatPromptTemplate:  # type: ignore[no-redef]
        def __init__(self, messages: list[tuple[str, str]]) -> None:
            self._messages = messages
            self.input_variables = sorted(
                {
                    field_name
                    for _, template in messages
                    for _, field_name, _, _ in Formatter().parse(template)
                    if field_name
                }
            )

        @classmethod
        def from_messages(cls, messages: list[tuple[str, str]]) -> ChatPromptTemplate:
            return cls(messages)

        def invoke(self, variables: dict[str, Any]) -> _PromptValue:
            classes = {"system": SystemMessage, "human": HumanMessage, "ai": BaseMessage}
            return _PromptValue(
                [
                    classes[role](content=template.format(**variables))
                    for role, template in self._messages
                ]
            )


__all__ = [
    "LANGCHAIN_AVAILABLE",
    "BaseMessage",
    "ChatPromptTemplate",
    "HumanMessage",
    "SystemMessage",
]
