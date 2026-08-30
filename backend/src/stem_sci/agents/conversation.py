"""Role-bounded multi-turn conversation for the six research Agents."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .runtime import StructuredGenerationError, StructuredGenerator


class ConversationDecision(BaseModel):
    """Candidate conversational decision; it has no workflow authority."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    reply: str = Field(min_length=1)
    extracted_updates: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    missing_requirements: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    next_action: Literal["ask_user", "candidate_ready", "show_progress", "fallback"]
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)
    llm_metadata_ref: str | None = None


class ConversationDraft(BaseModel):
    """Strict model returned by the LLM before Controller validation."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1)
    extracted_updates: dict[str, Any] = Field(default_factory=dict)
    missing_requirements: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    next_action: Literal["ask_user", "candidate_ready", "show_progress"] = "ask_user"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    conversation_id: str
    agent_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    messages: list[str] = Field(default_factory=list)


class ConversationStateStore(Protocol):
    def get(self, project_id: str, conversation_id: str, agent_id: str) -> ConversationState | None: ...
    def put(self, state: ConversationState) -> ConversationState: ...


class InMemoryConversationStateStore:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str, str], ConversationState] = {}

    def get(self, project_id: str, conversation_id: str, agent_id: str) -> ConversationState | None:
        return self._states.get((project_id, conversation_id, agent_id))

    def put(self, state: ConversationState) -> ConversationState:
        self._states[(state.project_id, state.conversation_id, state.agent_id)] = state
        return state


class SQLiteConversationStateStore:
    """Durable project conversation state without storing provider secrets."""

    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as connection:
            connection.execute(
                """create table if not exists agent_conversation_state (
                    project_id text not null, conversation_id text not null,
                    agent_id text not null, body text not null,
                    primary key (project_id, conversation_id, agent_id)
                )"""
            )

    def get(self, project_id: str, conversation_id: str, agent_id: str) -> ConversationState | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "select body from agent_conversation_state where project_id=? and conversation_id=? and agent_id=?",
                (project_id, conversation_id, agent_id),
            ).fetchone()
        return ConversationState.model_validate_json(row[0]) if row else None

    def put(self, state: ConversationState) -> ConversationState:
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """insert into agent_conversation_state(project_id, conversation_id, agent_id, body)
                values (?, ?, ?, ?) on conflict(project_id, conversation_id, agent_id)
                do update set body=excluded.body""",
                (state.project_id, state.conversation_id, state.agent_id, state.model_dump_json()),
            )
        return state


ROLE_REQUIREMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "mentor_planning": (("population", "研究对象"), ("context", "研究场景"), ("intervention", "干预方法"), ("comparator", "对照条件"), ("primary_outcome", "主要指标")),
    "evidence_review": (("search_goal", "检索目标"), ("date_range", "文献范围"), ("sources", "证据来源"), ("evidence_types", "证据类型")),
    "research_design": (("sample", "样本"), ("variables", "变量"), ("measurement", "测量指标"), ("design", "研究设计"), ("ethics", "伦理要求")),
    "data_analysis": (("dataset", "数据文件"), ("variables", "变量角色"), ("missing_data", "缺失值处理"), ("analysis_mode", "分析模式"), ("privacy", "隐私规则")),
    "paper_writing": (("scope", "写作范围"), ("languages", "语言版本"), ("target_format", "目标格式"), ("claim_boundary", "主张边界")),
    "independent_review": (("scope", "审查范围"), ("focus", "审查重点"), ("release_threshold", "发布门槛")),
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "population": ("研究对象", "研究人群", "样本对象"),
    "context": ("研究场景", "应用场景", "场景"),
    "intervention": ("干预与对照", "干预方法", "干预"),
    "comparator": ("对照条件", "对照组", "对照"),
    "primary_outcome": ("主要指标", "主要结果", "结果指标"),
    "search_goal": ("检索目标", "检索问题"),
    "date_range": ("文献范围", "时间范围"),
    "sources": ("证据来源", "来源"),
    "evidence_types": ("证据类型", "文献类型"),
    "sample": ("样本", "样本量"),
    "variables": ("变量", "变量角色"),
    "measurement": ("测量指标", "测量"),
    "design": ("研究设计", "设计"),
    "ethics": ("伦理要求", "伦理"),
    "dataset": ("数据文件", "数据集", "CSV"),
    "missing_data": ("缺失值处理", "缺失值"),
    "analysis_mode": ("分析模式", "统计方法"),
    "privacy": ("隐私规则", "隐私"),
    "scope": ("写作范围", "审查范围", "范围"),
    "languages": ("语言版本", "语言"),
    "target_format": ("目标格式", "投稿格式"),
    "claim_boundary": ("主张边界", "结论边界"),
    "focus": ("审查重点", "重点"),
    "release_threshold": ("发布门槛", "发布标准"),
}


class AgentConversationService:
    def __init__(
        self,
        *,
        state_store: ConversationStateStore,
        generator: StructuredGenerator | None = None,
        model: str | None = None,
    ) -> None:
        self.state_store = state_store
        self.generator = generator
        self.model = model

    def respond(
        self,
        *,
        project_id: str,
        conversation_id: str,
        agent_id: str,
        user_message: str,
        project_context: Mapping[str, Any] | None = None,
    ) -> ConversationDecision:
        if agent_id not in ROLE_REQUIREMENTS:
            raise ValueError(f"unknown conversational agent: {agent_id}")
        message = user_message.strip()
        if not message:
            raise ValueError("user_message must not be empty")
        previous = self.state_store.get(project_id, conversation_id, agent_id)
        state = previous or ConversationState(
            project_id=project_id, conversation_id=conversation_id, agent_id=agent_id
        )
        fallback_updates = self._extract_updates(message, agent_id)
        merged = {**state.values, **fallback_updates}
        draft: ConversationDraft | None = None
        metadata_ref: str | None = None
        if self.generator is not None and self.model:
            try:
                generated = self.generator.generate(
                    system_prompt=self._system_prompt(agent_id),
                    user_prompt=self._user_prompt(agent_id, message, merged, state.messages, project_context),
                    response_model=ConversationDraft,
                    model=self.model,
                    prompt_version=f"{agent_id}-conversation-v1",
                )
                draft = generated.parsed_output
                metadata_ref = f"llm-metadata://{generated.request_id}"
                if isinstance(draft, ConversationDraft):
                    merged.update(self._allowed_updates(agent_id, draft.extracted_updates))
            except (StructuredGenerationError, ValueError):
                draft = None
        missing = self._missing(agent_id, merged)
        questions = [label + "是什么？" for _, label in ROLE_REQUIREMENTS[agent_id] if _ in missing]
        if draft is not None:
            questions = [question for question in draft.questions if question.strip()][:5] or questions
            reply = draft.reply
            next_action = draft.next_action if not missing else "ask_user"
            confidence = draft.confidence
            risk_flags = list(draft.risk_flags)
        else:
            reply = self._fallback_reply(agent_id, merged, missing)
            next_action = "candidate_ready" if not missing else "ask_user"
            confidence = 0.72 if fallback_updates else 0.45
            risk_flags = ["MODEL_UNAVAILABLE"] if self.generator is None or not self.model else ["MODEL_GENERATION_FAILED"]
        updated = state.model_copy(update={"values": merged, "messages": [*state.messages, message][-12:]})
        self.state_store.put(updated)
        return ConversationDecision(
            agent_id=agent_id,
            reply=reply,
            extracted_updates=self._allowed_updates(agent_id, {**fallback_updates, **(draft.extracted_updates if draft else {})}),
            current_state=merged,
            missing_requirements=missing,
            questions=questions,
            next_action=next_action,
            confidence=confidence,
            risk_flags=list(dict.fromkeys(risk_flags)),
            llm_metadata_ref=metadata_ref,
        )

    @staticmethod
    def _missing(agent_id: str, values: Mapping[str, Any]) -> list[str]:
        return [key for key, _ in ROLE_REQUIREMENTS[agent_id] if not str(values.get(key, "")).strip()]

    @staticmethod
    def _allowed_updates(agent_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {key for key, _ in ROLE_REQUIREMENTS[agent_id]}
        return {key: value for key, value in updates.items() if key in allowed and isinstance(value, (str, int, float, bool, list, dict)) and str(value).strip()}

    @staticmethod
    def _extract_updates(message: str, agent_id: str) -> dict[str, str]:
        updates: dict[str, str] = {}
        for key, aliases in _ALIASES.items():
            if key not in {item[0] for item in ROLE_REQUIREMENTS[agent_id]}:
                continue
            alias_pattern = "|".join(re.escape(alias) for alias in aliases)
            match = re.search(rf"(?:{alias_pattern})\s*[:：]\s*([^；;。\n]+)", message, flags=re.IGNORECASE)
            if match is None:
                match = re.search(rf"(?:{alias_pattern})\s*(?:改为|改成|换成)\s*([^；;。\n]+)", message, flags=re.IGNORECASE)
            if match:
                updates[key] = match.group(1).strip()
        return updates

    @staticmethod
    def _fallback_reply(agent_id: str, values: Mapping[str, Any], missing: list[str]) -> str:
        labels = dict(ROLE_REQUIREMENTS[agent_id])
        if missing:
            known = "、".join(labels[key] for key in labels if key in values)
            prefix = f"我已记录{known}。" if known else "我先帮你梳理这一阶段的必要信息。"
            return prefix + "为了继续，需要补充：" + "、".join(labels[key] for key in missing) + "。"
        return "这一阶段所需信息已齐全。我可以据此生成候选方案，生成后仍需你审核才能进入下一阶段。"

    @staticmethod
    def _system_prompt(agent_id: str) -> str:
        labels = "、".join(label for _, label in ROLE_REQUIREMENTS[agent_id])
        return (
            f"你是 STEM-SCI 的 {agent_id} 专家。围绕本阶段需求（{labels}）理解用户自然语言，"
            "只提问尚缺信息并合并用户最新表述。输出严格 JSON。不得批准、拒绝、推进工作流、冻结数据、执行代码、发布结果或编造证据。"
        )

    @staticmethod
    def _user_prompt(agent_id: str, message: str, state: Mapping[str, Any], history: list[str], context: Mapping[str, Any] | None) -> str:
        return json.dumps({"agent_id": agent_id, "user_message": message, "current_state": state, "history": history[-6:], "project_context": dict(context or {})}, ensure_ascii=False)
