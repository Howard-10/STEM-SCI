"""Deterministic validation of Agent results before workflow merging."""

from __future__ import annotations

from stem_sci.agents.contracts import AgentCapability, AgentResult


def validate_agent_result(result: AgentResult, capability: AgentCapability) -> AgentResult:
    """Reject role mismatches and candidate outputs outside the Controller allow-list."""
    if result.agent_id != capability.agent_id:
        raise ValueError("AgentResult agent_id does not match the registered capability")

    allowed_outputs = set(capability.allowed_output_types)
    for artifact_ref in result.candidate_artifact_refs:
        parts = artifact_ref.split("/")
        if len(parts) < 4 or parts[0] != "candidate:":
            raise ValueError("candidate artifact references must use candidate:// scheme")
        output_type = parts[-1]
        if output_type not in allowed_outputs:
            raise ValueError(f"agent produced output outside capability: {output_type}")

    allowed_tools = set(capability.allowed_tool_capabilities)
    for tool_request in result.tool_requests:
        if not tool_request.startswith("request://"):
            raise ValueError("tool requests must use request:// scheme")
        capability_name = tool_request.removeprefix("request://")
        if capability_name not in allowed_tools:
            raise ValueError(f"agent requested tool outside capability: {capability_name}")
    return result
