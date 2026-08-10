"""Thread-scoped messages and loss-aware summarization."""

from __future__ import annotations

import re
from collections.abc import Sequence
from threading import RLock
from typing import TYPE_CHECKING, Any, NotRequired, Protocol, TypedDict

from stem_sci.compat.langchain import BaseMessage
from stem_sci.context.tokens import estimate_message_tokens

from .models import ConversationSummary

if TYPE_CHECKING:
    from stem_sci.context.models import RuntimeContext


class ConversationState(TypedDict):
    """Reference-only state shape compatible with a LangGraph message state."""

    messages: list[BaseMessage]
    summary: NotRequired[dict[str, Any]]


class _ThreadBackend(Protocol):
    def append(self, thread_key: str, messages: Sequence[BaseMessage]) -> None: ...
    def get(self, thread_key: str) -> ConversationState: ...
    def compact(
        self, thread_key: str, keep: Sequence[BaseMessage], summary: ConversationSummary
    ) -> None: ...


class _MemoryThreadBackend:
    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._lock = RLock()

    def append(self, thread_key: str, messages: Sequence[BaseMessage]) -> None:
        with self._lock:
            state = self._states.setdefault(thread_key, {"messages": []})
            known = {message.id for message in state["messages"] if message.id}
            state["messages"].extend(
                message for message in messages if not message.id or message.id not in known
            )

    def get(self, thread_key: str) -> ConversationState:
        with self._lock:
            state = self._states.get(thread_key)
            if state is None:
                return {"messages": []}
            result: ConversationState = {"messages": list(state["messages"])}
            if "summary" in state:
                result["summary"] = dict(state["summary"])
            return result

    def compact(
        self, thread_key: str, keep: Sequence[BaseMessage], summary: ConversationSummary
    ) -> None:
        with self._lock:
            self._states[thread_key] = {
                "messages": list(keep),
                "summary": summary.model_dump(mode="json"),
            }


class _LangGraphThreadBackend:
    """Native checkpointer backend, instantiated only when LangGraph is installed."""

    def __init__(self, checkpointer: Any | None = None) -> None:
        from langchain_core.messages import RemoveMessage
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import (
            END,
            START,
            MessagesState,
            StateGraph,
        )
        from langgraph.graph.message import REMOVE_ALL_MESSAGES

        class NativeState(MessagesState, total=False):
            summary: dict[str, Any]

        builder = StateGraph(NativeState)
        builder.add_node("record", lambda state: {})
        builder.add_edge(START, "record")
        builder.add_edge("record", END)
        self.graph: Any = builder.compile(checkpointer=checkpointer or InMemorySaver())
        self.RemoveMessage = RemoveMessage
        self.remove_all = REMOVE_ALL_MESSAGES

    @staticmethod
    def _config(thread_key: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_key}}

    def append(self, thread_key: str, messages: Sequence[BaseMessage]) -> None:
        self.graph.invoke({"messages": list(messages)}, config=self._config(thread_key))

    def get(self, thread_key: str) -> ConversationState:
        values = self.graph.get_state(self._config(thread_key)).values
        result: ConversationState = {"messages": list(values.get("messages", []))}
        if values.get("summary"):
            result["summary"] = values["summary"]
        return result

    def compact(
        self, thread_key: str, keep: Sequence[BaseMessage], summary: ConversationSummary
    ) -> None:
        updates = {
            "messages": [self.RemoveMessage(id=self.remove_all), *keep],
            "summary": summary.model_dump(mode="json"),
        }
        self.graph.update_state(self._config(thread_key), updates)


class ShortTermMemory:
    """Maintains one checkpointer thread per user/project/thread identity."""

    def __init__(
        self,
        *,
        history_budget_tokens: int = 4_000,
        trigger_ratio: float = 0.8,
        keep_messages: int = 8,
        summarizer: Any | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self.history_budget_tokens = history_budget_tokens
        self.trigger_ratio = trigger_ratio
        self.keep_messages = keep_messages
        self.summarizer = summarizer
        self._backend: _ThreadBackend
        try:
            self._backend = _LangGraphThreadBackend(checkpointer)
        except ImportError:
            self._backend = _MemoryThreadBackend()

    @staticmethod
    def _key(identity: RuntimeContext) -> str:
        return f"{identity.user_id}:{identity.project_id}:{identity.thread_id}"

    def append(self, identity: RuntimeContext, messages: Sequence[BaseMessage]) -> None:
        self._backend.append(self._key(identity), messages)

    def state(self, identity: RuntimeContext) -> ConversationState:
        return self._backend.get(self._key(identity))

    def should_summarize(self, identity: RuntimeContext, force: bool = False) -> bool:
        if force:
            return True
        return estimate_message_tokens(self.state(identity)["messages"]) >= int(
            self.history_budget_tokens * self.trigger_ratio
        )

    def summarize(self, identity: RuntimeContext, force: bool = False) -> ConversationSummary:
        state = self.state(identity)
        existing = (
            ConversationSummary.model_validate(state["summary"]) if state.get("summary") else None
        )
        if not self.should_summarize(identity, force=force):
            return existing or ConversationSummary()
        messages = state["messages"]
        keep = messages[-self.keep_messages :]
        compress = (
            messages[: -self.keep_messages] if len(messages) > self.keep_messages else messages
        )
        summary = self._summarize_messages(compress, existing)
        self._backend.compact(self._key(identity), keep, summary)
        return summary

    def _summarize_messages(
        self, messages: Sequence[BaseMessage], existing: ConversationSummary | None
    ) -> ConversationSummary:
        if self.summarizer is not None:
            result = self.summarizer(messages, existing)
            return (
                result
                if isinstance(result, ConversationSummary)
                else ConversationSummary.model_validate(result)
            )
        text_rows, goals, decisions, issues, evidence, failures, ids = [], [], [], [], [], [], []
        for index, message in enumerate(messages):
            content = message.content if isinstance(message.content, str) else str(message.content)
            ids.append(str(message.id or index))
            text_rows.append(content[:400])
            if re.search(r"\u76ee\u6807|\u5e0c\u671b\u5b8c\u6210|goal", content, re.IGNORECASE):
                goals.append(content[:300])
            if re.search(
                r"\u5df2\u6279\u51c6|\u786e\u8ba4\u91c7\u7528|\u51b3\u5b9a|approved",
                content,
                re.IGNORECASE,
            ):
                decisions.append(content[:300])
            if re.search(
                r"\u5f85\u89e3\u51b3|\u5c1a\u672a|\u672a\u89e3\u51b3|unresolved",
                content,
                re.IGNORECASE,
            ):
                issues.append(content[:300])
            evidence.extend(
                re.findall(
                    r"(?:evidence|\u6765\u6e90|\u8bc1\u636e)[_:#\uff1a-]*[A-Za-z0-9_.-]+",
                    content,
                    re.IGNORECASE,
                )
            )
            if re.search(r"\u5931\u8d25|\u9519\u8bef|blocked|failed", content, re.IGNORECASE):
                failures.append(content[:300])
        return ConversationSummary(
            user_goals=tuple(dict.fromkeys([*(existing.user_goals if existing else ()), *goals])),
            approved_decisions=tuple(
                dict.fromkeys([*(existing.approved_decisions if existing else ()), *decisions])
            ),
            unresolved_issues=tuple(
                dict.fromkeys([*(existing.unresolved_issues if existing else ()), *issues])
            ),
            evidence_refs=tuple(
                dict.fromkeys([*(existing.evidence_refs if existing else ()), *evidence])
            ),
            failure_reasons=tuple(
                dict.fromkeys([*(existing.failure_reasons if existing else ()), *failures])
            ),
            process_summary=" | ".join(text_rows)[-4_000:],
            summarized_message_ids=tuple(
                dict.fromkeys([*(existing.summarized_message_ids if existing else ()), *ids])
            ),
        )
