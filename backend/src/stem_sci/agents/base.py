"""Common deterministic scaffold used by the six Phase 1 agents."""

from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import JsonValue

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
    skill_ids: ClassVar[tuple[str, ...]] = ()
    tool_ids: ClassVar[tuple[str, ...]] = ()
    allowed_output_types: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def capability(cls) -> AgentCapability:
        return AgentCapability(
            agent_id=cls.agent_id,
            supported_task_types=list(cls.supported_task_types),
            allowed_tool_capabilities=list(cls.allowed_tool_capabilities),
            skill_ids=list(cls.skill_ids),
            tool_ids=list(cls.tool_ids),
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
        tool_requests: list[ToolRequest] = []
        for index, tool in enumerate(permitted_tools):
            payload = self._default_tool_payload(tool, agent_input)
            if payload is None:
                continue
            tool_requests.append(
                ToolRequest(
                    request_id=f"{agent_input.agent_run_id}:tool:{index}",
                    capability=tool,
                    input_payload=payload,
                    reason=f"Agent {self.agent_id} requests the {tool} capability.",
                )
            )
        return AgentResult(
            agent_run_id=agent_input.agent_run_id,
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            candidate_artifact_refs=refs,
            tool_requests=tool_requests,
            approval_requests=[],
            risk_flags=risk_flags,
            unresolved_questions=unresolved_questions,
            recommendations=recommendations,
            confidence=0.5 if refs else 0.0,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _default_tool_payload(
        tool: str, agent_input: AgentInput
    ) -> dict[str, JsonValue] | None:
        """Supply only reference-level defaults until an Agent skill fills inputs."""
        if tool == "context_bundle_read@v1":
            if "://" in agent_input.context_bundle_ref:
                return None
            return {"context_id": agent_input.context_bundle_ref}
        if tool == "knowledge_base_search@v1":
            return {"query": agent_input.task_ref, "limit": 10}
        if tool in {
            "source_verification_checker@v1",
            "evidence_ref_validate@v1",
            "bounded_synthesis_validator@v1",
            "python_analysis_sandbox@v1",
            "result_validation_checker@v1",
        }:
            return None
        if tool == "research_question_validator@v1":
            return {"question": agent_input.task_ref}
        if tool == "protocol_schema_validator@v1":
            return {"protocol_ref": agent_input.context_bundle_ref}
        if tool in {"dataset_schema_profile@v1", "data_quality_audit@v1"}:
            return {"dataset_ref": agent_input.context_bundle_ref}
        if tool.startswith("manuscript_renderer_"):
            return {"graph_ref": agent_input.context_bundle_ref, "outline_ref": agent_input.context_bundle_ref}
        if tool.endswith("_audit@v1") or tool in {"citation_audit@v1", "evidence_reference_audit@v1"}:
            return {"manuscript_ref": agent_input.context_bundle_ref}
        if tool.endswith(("_validator@v1", "_checker@v1")):
            return {"context_ref": agent_input.context_bundle_ref}
        if "@" in tool:
            return {"context_ref": agent_input.context_bundle_ref}
        return None
