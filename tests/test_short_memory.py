"""Short-term compaction invariants."""

from stem_sci.compat.langchain import HumanMessage
from stem_sci.context.models import RuntimeContext
from stem_sci.memory.short_term import ShortTermMemory


def test_summary_preserves_decisions_and_keeps_recent_messages() -> None:
    identity = RuntimeContext(user_id="u", project_id="p", thread_id="t", run_id="r")
    memory = ShortTermMemory(history_budget_tokens=100, keep_messages=8)
    messages = [
        HumanMessage(content=f"process message {i} " + "content " * 30, id=f"m{i}")
        for i in range(11)
    ]
    messages.insert(0, HumanMessage(content="Approved quasi-experimental design", id="decision"))
    memory.append(identity, messages)
    summary = memory.summarize(identity)
    state = memory.state(identity)
    assert any("quasi-experimental" in item for item in summary.approved_decisions)
    assert len(state["messages"]) == 8
    assert "decision" in summary.summarized_message_ids
