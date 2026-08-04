"""Common deterministic scaffold used by the six Phase 1 agents."""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from typing import ClassVar

from .contracts import AgentCapability, AgentInput, AgentResult, ToolRequest

FORBIDDEN_AGENT_ACTIONS: tuple[str, ...] = (
    "new_current_stage",
    "approved",
    "freeze_dataset",
    "official_result",
    "publish",
)


class BaseAgent(ABC):
    """A role boundary and proposal generator, not an autonomous controller.

    Phase 1 intentionally has no LLM call.  ``run`` creates deterministic
    candidate references so the contracts and permissions can be tested before
    a provider and real operators are connected.
    """

    agent_id: ClassVar[str]
    agent_version: ClassVar[str] = "phase1-scaffold"
    supported_task_types: ClassVar[tuple[str, ...]] = ()
    allowed_tool_capabilities: ClassVar[tuple[str, ...]] = ()
    allowed_output_types: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def capability(cls) -> AgentCapability:
        return AgentCapability(
            agent_id=cls.agent_id,
            supported_task_types=list(cls.supported_task_types),
            allowed_tool_capabilities=list(cls.allowed_tool_capabilities),
            allowed_output_types=list(cls.allowed_output_types),
            forbidden_actions=list(FORBIDDEN_AGENT_ACTIONS),
            read_only_global_state=True,
        )

    def run(self, agent_input: AgentInput) -> AgentResult:
        """Return candidate artifact references within the supplied allow-list."""

        allowed_outputs = set(agent_input.allowed_output_types)
        candidate_types = [
            output_type for output_type in self.allowed_output_types if output_type in allowed_outputs
        ]
        missing_outputs = [
            output_type for output_type in self.allowed_output_types if output_type not in allowed_outputs
        ]
        permitted_tools = [
            capability
            for capability in self.allowed_tool_capabilities
            if capability in set(agent_input.allowed_tool_capabilities)
        ]
        denied_tools = [
            capability
            for capability in self.allowed_tool_capabilities
            if capability not in set(agent_input.allowed_tool_capabilities)
        ]

        risk_flags: list[str] = []
        unresolved_questions: list[str] = []
        if missing_outputs:
            risk_flags.append("OUTPUT_CAPABILITY_NOT_GRANTED")
            unresolved_questions.append(
                "Controller must grant output capabilities before all role outputs can be proposed."
            )
        if denied_tools:
            risk_flags.append("TOOL_CAPABILITY_NOT_GRANTED")
            unresolved_questions.append("Controller must authorize requested operators before execution.")

        refs = [
            f"candidate://{self.agent_id}/{agent_input.task_ref}/{output_type}"
            for output_type in candidate_types
        ]
        recommendations = [
            "Controller must validate candidate artifacts with the applicable Gate before progression."
        ]
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=refs,
            tool_requests=[
                ToolRequest(
                    request_id=f"{agent_input.agent_run_id}:tool:{index}",
                    capability=tool,
                    reason=f"Agent {self.agent_id} requests the {tool} capability.",
                )
                for index, tool in enumerate(permitted_tools)
            ],
            approval_requests=[],
            risk_flags=risk_flags,
            unresolved_questions=unresolved_questions,
            recommendations=recommendations,
            confidence=0.5 if refs else 0.0,
            created_at=datetime.now(UTC),
        )
