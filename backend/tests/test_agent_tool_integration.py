from stem_sci.api import workflow_controller


def test_agent_capability_exposes_skill_and_tool_ids() -> None:
    capabilities = workflow_controller.list_agent_capabilities()
    evidence = next(item for item in capabilities if item.agent_id == "evidence_review")
    assert "bounded_corpus_review@v1" in evidence.skill_ids
    assert "knowledge_base_search@v1" in evidence.tool_ids


def test_default_gateway_registry_contains_all_bound_tools() -> None:
    registry = workflow_controller.tool_gateway.tool_registry
    missing = [
        tool_ref
        for capability in workflow_controller.list_agent_capabilities()
        for tool_ref in capability.tool_ids
        if not _registered(registry, tool_ref)
    ]
    assert missing == []


def test_agents_authorize_every_tool_declared_by_their_skills() -> None:
    registry = workflow_controller.tool_gateway.skill_registry
    for capability in workflow_controller.list_agent_capabilities():
        bound_tools = {
            tool_ref
            for manifest in registry.list()
            if capability.agent_id in manifest.agent_ids
            for tool_ref in manifest.required_tool_ids
        }
        assert set(capability.tool_ids) == bound_tools
        assert bound_tools.issubset(capability.allowed_tool_capabilities)


def test_data_analysis_agent_exposes_restricted_python_skill() -> None:
    capability = next(
        item
        for item in workflow_controller.list_agent_capabilities()
        if item.agent_id == "data_analysis"
    )
    assert "statistical_analysis_execution@v1" in capability.skill_ids
    assert "python_analysis_sandbox@v1" in capability.tool_ids


def _registered(registry, reference: str) -> bool:
    tool_id, version = reference.split("@", 1)
    try:
        registry.get(tool_id, version)
    except KeyError:
        return False
    return True
