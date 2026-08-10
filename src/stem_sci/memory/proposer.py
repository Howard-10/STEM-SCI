"""Conservative memory proposal with optional LangChain structured output."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from stem_sci.compat.langchain import BaseMessage
from stem_sci.prompts.defaults import create_default_registry
from stem_sci.prompts.registry import PromptRegistry

from .models import MemoryCandidate, MemoryCandidateBatch, MemoryKind, MemoryScope, Sensitivity
from .policy import classify_sensitivity


def _serialize(messages: Sequence[BaseMessage]) -> str:
    rows = []
    for index, message in enumerate(messages):
        content = message.content if isinstance(message.content, str) else str(message.content)
        rows.append(f"[{message.id or index} role={message.type}] {content}")
    return "\n".join(rows)


class MemoryProposer:
    """Proposes candidates; it never writes confirmed memory."""

    def __init__(
        self, model: Any | None = None, prompts: PromptRegistry | None = None, max_retries: int = 2
    ) -> None:
        self.model = model
        self.prompts = prompts or create_default_registry()
        self.max_retries = max_retries

    def propose(self, messages: Sequence[BaseMessage]) -> list[MemoryCandidate]:
        if self.model is None:
            return self._deterministic_proposals(messages)
        prompt_messages = self.prompts.render(
            "memory.extract_candidates", "1.0.0", {"messages": _serialize(messages)}
        )
        for _ in range(self.max_retries + 1):
            try:
                structured_model = self.model.with_structured_output(MemoryCandidateBatch)
                result = structured_model.invoke(prompt_messages)
                batch = (
                    result
                    if isinstance(result, MemoryCandidateBatch)
                    else MemoryCandidateBatch.model_validate(result)
                )
                return [
                    candidate
                    for candidate in batch.candidates
                    if classify_sensitivity(candidate.content) is not Sensitivity.PROHIBITED
                ]
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        return []

    @staticmethod
    def _deterministic_proposals(messages: Sequence[BaseMessage]) -> list[MemoryCandidate]:
        proposals = []
        seen = set()
        preference = re.compile(
            r"(?:\u6211\u5e0c\u671b|\u6211\u504f\u597d|\u6211\u559c\u6b22|"
            r"\u4ee5\u540e\u8bf7|\u8bf7\u4e00\u76f4|I prefer|Please always)(.{2,200})",
            re.IGNORECASE,
        )
        decision = re.compile(
            r"(?:\u5df2\u6279\u51c6|\u786e\u8ba4\u91c7\u7528|\u51b3\u5b9a\u4f7f\u7528|"
            r"\u786e\u5b9a\u91c7\u7528|approved|we decided to use)(.{2,300})",
            re.IGNORECASE,
        )
        for index, message in enumerate(messages):
            content = message.content if isinstance(message.content, str) else str(message.content)
            source_id = str(message.id or index)
            for pattern, scope, kind in (
                (preference, MemoryScope.USER, MemoryKind.USER_PREFERENCE),
                (decision, MemoryScope.PROJECT, MemoryKind.APPROVED_DECISION),
            ):
                match = pattern.search(content)
                if not match:
                    continue
                candidate_content = match.group(0).strip().rstrip("?.!")
                if (
                    candidate_content in seen
                    or classify_sensitivity(candidate_content) is Sensitivity.PROHIBITED
                ):
                    continue
                seen.add(candidate_content)
                proposals.append(
                    MemoryCandidate(
                        scope=scope,
                        kind=kind,
                        content=candidate_content,
                        source_message_ids=(source_id,),
                    )
                )
        return proposals
