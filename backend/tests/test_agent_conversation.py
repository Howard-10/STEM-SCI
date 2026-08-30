from __future__ import annotations

from stem_sci.agents.conversation import (
    AgentConversationService,
    ConversationState,
    InMemoryConversationStateStore,
)
from stem_sci.agents.runtime import FakeLLMProvider, StructuredGenerator


def test_fallback_only_asks_for_missing_requirements() -> None:
    service = AgentConversationService(state_store=InMemoryConversationStateStore())

    decision = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="mentor_planning",
        user_message="研究对象：大一物理师范生；研究场景：大学物理实验室",
    )

    assert decision.extracted_updates == {
        "population": "大一物理师范生",
        "context": "大学物理实验室",
    }
    assert decision.missing_requirements == ["intervention", "comparator", "primary_outcome"]
    assert len(decision.questions) == 3
    assert "研究对象" not in "".join(decision.questions)
    assert decision.next_action == "ask_user"


def test_follow_up_merges_state_and_replaces_changed_value() -> None:
    service = AgentConversationService(state_store=InMemoryConversationStateStore())

    first = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="mentor_planning",
        user_message="研究对象：本科生；研究场景：实验室；干预：AI支架；对照：传统教学；主要指标：迁移得分",
    )
    second = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="mentor_planning",
        user_message="对照改为常规提示",
    )

    assert first.missing_requirements == []
    assert second.current_state["comparator"] == "常规提示"
    assert second.missing_requirements == []
    assert second.next_action == "candidate_ready"


def test_model_decision_is_typed_and_cannot_request_approval() -> None:
    provider = FakeLLMProvider(
        [
            {
                "reply": "还需要确认对照条件。",
                "extracted_updates": {"population": "本科生"},
                "missing_requirements": ["comparator"],
                "questions": ["对照条件是什么？"],
                "next_action": "ask_user",
                "confidence": 0.88,
                "risk_flags": [],
            }
        ]
    )
    service = AgentConversationService(
        generator=StructuredGenerator(provider),
        model="test-model",
        state_store=InMemoryConversationStateStore(),
    )

    decision = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="evidence_review",
        user_message="帮我找文献",
    )

    assert decision.reply == "还需要确认对照条件。"
    assert decision.next_action == "ask_user"
    assert decision.llm_metadata_ref == "llm-metadata://fake-llm-request-1"


def test_model_action_variants_are_normalized_to_safe_actions() -> None:
    provider = FakeLLMProvider(
        [
            {
                "reply": "还需要补充研究对象。",
                "extracted_updates": {},
                "missing_requirements": ["population"],
                "questions": ["研究对象是什么？"],
                "next_action": "awaiting_population_data",
                "confidence": 0.8,
                "risk_flags": [],
            }
        ]
    )
    service = AgentConversationService(
        generator=StructuredGenerator(provider),
        model="test-model",
        state_store=InMemoryConversationStateStore(),
    )

    decision = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="mentor_planning",
        user_message="请继续梳理",
    )

    assert decision.next_action == "ask_user"
    assert decision.llm_metadata_ref == "llm-metadata://fake-llm-request-1"


def test_model_question_objects_and_missing_reply_are_normalized() -> None:
    provider = FakeLLMProvider(
        [
            {
                "questions": [{"question": "研究对象是什么？", "key": "研究对象"}],
                "next_action": "awaiting_population_data",
            }
        ]
    )
    service = AgentConversationService(
        generator=StructuredGenerator(provider),
        model="test-model",
        state_store=InMemoryConversationStateStore(),
    )

    decision = service.respond(
        project_id="p1",
        conversation_id="c1",
        agent_id="mentor_planning",
        user_message="请梳理研究信息",
    )

    assert decision.questions == ["研究对象是什么？"]
    assert decision.reply
    assert decision.next_action == "ask_user"
    assert decision.llm_metadata_ref == "llm-metadata://fake-llm-request-1"


def test_all_six_agents_have_role_specific_requirements() -> None:
    service = AgentConversationService(state_store=InMemoryConversationStateStore())
    for agent_id in (
        "mentor_planning",
        "evidence_review",
        "research_design",
        "data_analysis",
        "paper_writing",
        "independent_review",
    ):
        decision = service.respond(
            project_id="p1",
            conversation_id=f"c-{agent_id}",
            agent_id=agent_id,
            user_message="我的研究思路需要进一步明确。",
        )
        assert decision.agent_id == agent_id
        assert decision.questions
        assert decision.next_action == "ask_user"
