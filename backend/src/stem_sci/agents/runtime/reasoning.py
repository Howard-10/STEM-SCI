"""Shared bounded LLM reasoning hook for specialist Agents."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .structured_generator import StructuredGenerator


class AgentReasoningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    key_decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class AgentReasoningPipeline:
    """Ask an LLM for role-bounded reasoning without granting control authority."""

    def __init__(self, generator: StructuredGenerator, model: str) -> None:
        self.generator = generator
        self.model = model

    def run(self, agent_id: str, agent_input: Any) -> tuple[AgentReasoningCandidate, str]:
        result = self.generator.generate(
            system_prompt=(
                f"You are the {agent_id} specialist in a governed research workflow. "
                "Reason only about the supplied task and references. Return a candidate "
                "summary, key decisions, open questions, and risks. Never approve, reject, "
                "change workflow state, fabricate evidence, execute code, or publish."
            ),
            user_prompt=(
                "Use the following structured task and conversation context:\n"
                + json.dumps(agent_input.model_dump(mode="json"), ensure_ascii=False)
            ),
            response_model=AgentReasoningCandidate,
            model=self.model,
            prompt_version=f"{agent_id}-reasoning-v1",
        )
        return result.parsed_output, result.request_id
