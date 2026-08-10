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

    candidate_refs = set(result.candidate_artifact_refs)
    seen_content_refs: set[str] = set()
    for candidate in result.candidate_artifacts:
        if candidate.candidate_ref not in candidate_refs:
            raise ValueError("candidate content ref is not a public candidate reference")
        if candidate.candidate_ref in seen_content_refs:
            raise ValueError("candidate content ref is duplicated")
        seen_content_refs.add(candidate.candidate_ref)
        output_type = candidate.candidate_ref.rsplit("/", maxsplit=1)[-1]
        if candidate.artifact_type != output_type:
            raise ValueError("candidate content type does not match candidate reference")
        if output_type not in allowed_outputs:
            raise ValueError(f"candidate content outside capability: {output_type}")

    allowed_tools = set(capability.allowed_tool_capabilities)
    for tool_request in result.tool_requests:
        capability_name = tool_request.capability
        if capability_name not in allowed_tools:
            raise ValueError(f"agent requested tool outside capability: {capability_name}")
    return result
