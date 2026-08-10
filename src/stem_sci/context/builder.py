"""Deterministic, budget-aware model context construction."""

from __future__ import annotations

from collections.abc import Sequence

from stem_sci.compat.langchain import BaseMessage, HumanMessage, SystemMessage
from stem_sci.memory.models import MemoryRecord
from stem_sci.prompts.defaults import create_default_registry
from stem_sci.prompts.registry import PromptRegistry

from .models import ContextPackage, ContextRequest, ContextTrace, EvidenceContext
from .tokens import estimate_message_tokens


class ContextBudgetError(ValueError):
    """Raised when non-droppable content cannot fit in the configured input budget."""


def _message_id(message: BaseMessage, index: int) -> str:
    return str(message.id or f"history_{index}")


def _untrusted_block(title: str, lines: Sequence[str]) -> str:
    return "<untrusted_context>\n" + title + "\n" + "\n".join(lines) + "\n</untrusted_context>"


class ContextBuilder:
    def __init__(self, prompts: PromptRegistry | None = None) -> None:
        self.prompts = prompts or create_default_registry()

    def build(self, request: ContextRequest) -> ContextPackage:
        base_manifest = self.prompts.manifest("context.base", request.prompt_version)
        base = self.prompts.render(
            "context.base",
            request.prompt_version,
            {
                "task": request.task,
                "forbidden_operations": "\n".join(request.forbidden_operations)
                or "None specified.",
                "output_requirements": request.output_requirements,
            },
        )
        decision_message = self._decisions(request)
        current = HumanMessage(
            content=request.user_message, id=f"current:{request.identity.run_id}"
        )
        protected = [*base, *([decision_message] if decision_message else []), current]
        if estimate_message_tokens(protected) > request.budget.input_limit:
            raise ContextBudgetError(
                "System policy, approved decisions, task, and current user message exceed the input limit"
            )

        summary = request.conversation_summary.strip()
        history = self._dedupe_history(request.recent_messages)[-8:]
        memories = self._valid_memories(request)
        evidence = self._dedupe_evidence(request.evidence)
        dropped: list[str] = []

        while True:
            messages = self._assemble(
                base, decision_message, summary, history, memories, evidence, current
            )
            tokens = estimate_message_tokens(messages)
            if tokens <= request.budget.input_limit:
                break
            if history:
                removed_history = history.pop(0)
                dropped.append(f"history:{_message_id(removed_history, 0)}")
            elif memories:
                removed_memory = memories.pop()
                dropped.append(f"memory:{removed_memory.memory_id}")
            elif evidence:
                removed_evidence = evidence.pop()
                dropped.append(f"evidence:{removed_evidence.evidence_id}")
            elif summary:
                summary = ""
                dropped.append("conversation_summary")
            else:
                raise ContextBudgetError("Context cannot fit without dropping protected content")

        included_ids = tuple(_message_id(message, index) for index, message in enumerate(history))
        trace = ContextTrace(
            user_id=request.identity.user_id,
            project_id=request.identity.project_id,
            thread_id=request.identity.thread_id,
            run_id=request.identity.run_id,
            selected_memory_ids=tuple(memory.memory_id for memory in memories),
            selected_evidence_ids=tuple(item.evidence_id for item in evidence),
            included_message_ids=included_ids,
            dropped=tuple(dropped),
            prompt_hashes={"context.base": base_manifest.content_hash},
            estimated_input_tokens=tokens,
            input_token_limit=request.budget.input_limit,
        )
        return ContextPackage(messages=messages, trace=trace)

    @staticmethod
    def _decisions(request: ContextRequest) -> SystemMessage | None:
        seen, lines = set(), []
        for decision in request.approved_decisions:
            if decision.decision_id not in seen:
                seen.add(decision.decision_id)
                lines.append(f"[{decision.decision_id}] {decision.content}")
        if not lines:
            return None
        return SystemMessage(
            content="Human-approved project decisions; preserve them verbatim:\n"
            + "\n".join(lines),
            id="approved-decisions",
        )

    @staticmethod
    def _dedupe_history(messages: list[BaseMessage]) -> list[BaseMessage]:
        seen, result = set(), []
        for index, message in enumerate(messages):
            key = _message_id(message, index)
            if key not in seen:
                seen.add(key)
                result.append(message)
        return result

    @staticmethod
    def _valid_memories(request: ContextRequest) -> list[MemoryRecord]:
        seen, result = set(), []
        for memory in request.memories:
            owned = memory.user_id == request.identity.user_id and (
                memory.project_id is None or memory.project_id == request.identity.project_id
            )
            if owned and memory.memory_id not in seen:
                seen.add(memory.memory_id)
                result.append(memory)
        return result[:6]

    @staticmethod
    def _dedupe_evidence(items: list[EvidenceContext]) -> list[EvidenceContext]:
        best: dict[str, EvidenceContext] = {}
        for item in items:
            if item.evidence_id not in best or item.relevance > best[item.evidence_id].relevance:
                best[item.evidence_id] = item
        return sorted(best.values(), key=lambda item: item.relevance, reverse=True)

    def _assemble(
        self,
        base: list[BaseMessage],
        decision: SystemMessage | None,
        summary: str,
        history: list[BaseMessage],
        memories: list[MemoryRecord],
        evidence: list[EvidenceContext],
        current: HumanMessage,
    ) -> list[BaseMessage]:
        messages = list(base)
        if decision:
            messages.append(decision)
        if summary:
            messages.append(
                HumanMessage(content=_untrusted_block("Conversation summary:", [summary]))
            )
        if history:
            lines = []
            for index, message in enumerate(history):
                content = (
                    message.content if isinstance(message.content, str) else str(message.content)
                )
                lines.append(f"[{_message_id(message, index)} role={message.type}] {content}")
            messages.append(HumanMessage(content=_untrusted_block("Recent conversation:", lines)))
        context_lines = [
            f"[memory:{memory.memory_id} kind={memory.kind.value}] {memory.content}"
            for memory in memories
        ]
        context_lines.extend(
            f"[evidence:{item.evidence_id} source={item.source} citation={item.citation}] {item.content}"
            for item in evidence
        )
        if context_lines:
            messages.extend(
                self.prompts.render(
                    "context.untrusted_data", "1.0.0", {"context_data": "\n".join(context_lines)}
                )
            )
        messages.append(current)
        return messages


_DEFAULT_BUILDER = ContextBuilder()


def build_context(request: ContextRequest) -> ContextPackage:
    return _DEFAULT_BUILDER.build(request)
