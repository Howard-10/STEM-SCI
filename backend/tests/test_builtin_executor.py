from pathlib import Path

from stem_sci.agents.contracts import ToolRequest
from stem_sci.agents.evidence_pipeline.models import BoundedEvidenceSynthesis
from stem_sci.context.models import EvidenceSearchRequest
from stem_sci.context.service import ContextService
from stem_sci.skills.builtin import BUILTIN_SKILLS
from stem_sci.skills.registry import SkillRegistry
from stem_sci.tools.builtin.executor import BuiltinToolExecutor
from stem_sci.tools.gateway import ToolGateway
from stem_sci.tools.models import ToolRunStatus
from stem_sci.tools.registry import ToolRegistry


def _gateway(tmp_path: Path) -> tuple[ToolGateway, ContextService]:
    service = ContextService(tmp_path)
    service.import_bytes("project-a", "physics.md", b"STEM_SCI_DEMO_SEED: true\nPhysics evidence")
    executor = BuiltinToolExecutor(service=service, project_root=tmp_path)
    gateway = ToolGateway(
        tool_registry=ToolRegistry.default(),
        skill_registry=SkillRegistry(BUILTIN_SKILLS),
        executor=executor,
    )
    return gateway, service


def test_gateway_executes_project_scoped_knowledge_search(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-1",
            capability="knowledge_base_search@v1",
            input_payload={"query": "physics", "limit": 10},
            reason="search imported evidence",
        ),
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.output_data is not None
    assert result.output_data["project_id"] == "project-a"


def test_gateway_blocks_cross_project_builtin_input(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-2",
            capability="artifact_resolve@v1",
            input_refs=["artifact-content://project-b/a/1"],
            reason="cross project probe",
        ),
    )
    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_gateway_executes_bounded_synthesis_validation(tmp_path: Path) -> None:
    gateway, service = _gateway(tmp_path)
    ref = service.search(EvidenceSearchRequest(project_id="project-a", query="physics"))[0].evidence
    verified = service.verify_source("project-a", ref.evidence_id, "tester", "checked")
    result = gateway.execute(
        project_id="project-a",
        agent_id="evidence_review",
        agent_run_id="run-1",
        request=ToolRequest(
            request_id="request-3",
            capability="bounded_synthesis_validator@v1",
            input_payload={
                "synthesis": BoundedEvidenceSynthesis(
                    synthesis_id="s1",
                    project_id="project-a",
                    summary="bounded summary",
                    evidence_refs=[verified.evidence_id],
                    corpus_limit="Only imported corpus.",
                ).model_dump(mode="json")
            },
            reason="validate bounded synthesis",
        ),
    )
    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.output_data is not None
    assert result.output_data["approved"] is True
