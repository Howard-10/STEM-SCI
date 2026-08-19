from pathlib import Path

import pytest

from stem_sci.agents.contracts import ToolRequest
from stem_sci.agents.evidence_pipeline.models import BoundedEvidenceSynthesis
from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.content_store import InMemoryArtifactContentStore
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
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
        executor=executor,
    )
    return gateway, service


def test_builtin_executor_dispatches_every_registered_tool(tmp_path: Path) -> None:
    service = ContextService(tmp_path)
    executor = BuiltinToolExecutor(service=service, project_root=tmp_path)
    missing = []
    for spec in ToolRegistry.default().list():
        result = executor.execute(
            spec,
            "project-a",
            "registry-audit",
            "run-registry-audit",
            ToolRequest(
                request_id=f"request-{spec.tool_id}",
                capability=f"{spec.tool_id}@{spec.tool_version}",
                reason="verify built-in dispatch coverage",
            ),
        )
        if result.error_code == "TOOL_EXECUTOR_UNAVAILABLE":
            missing.append(spec.tool_id)

    assert missing == []


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


def test_gateway_persists_candidate_tool_output_as_project_content(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="research_design",
        agent_run_id="run-design",
        request=ToolRequest(
            request_id="request-design",
            capability="research_question_validator@v1",
            input_payload={"question": "How does guided coding affect transfer?"},
            reason="validate the candidate research question",
        ),
    )

    assert result.status is ToolRunStatus.SUCCEEDED
    assert len(result.output_content_refs) == 1
    assert gateway.artifact_content_store is not None
    contents = gateway.artifact_content_store.list_project("project-a")
    assert len(contents) == 1
    assert contents[0].body["output_type"] == "ValidationReport"


@pytest.mark.parametrize(
    "capability,payload",
    [
        ("research_scope_validator@v1", {"research_intent": "Physics transfer"}),
        ("feasibility_checker@v1", {"research_intent": "Physics transfer"}),
    ],
)
def test_gateway_executes_planning_tools(
    tmp_path: Path, capability: str, payload: dict[str, str]
) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="mentor_planning",
        agent_run_id="run-planning",
        request=ToolRequest(
            request_id=f"request-{capability}",
            capability=capability,
            input_payload=payload,
            reason="validate the planning candidate",
        ),
    )

    assert result.status is ToolRunStatus.SUCCEEDED
    assert result.output_content_refs


def test_gateway_returns_typed_failure_for_missing_python_request(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="data_analysis",
        agent_run_id="run-analysis",
        request=ToolRequest(
            request_id="request-python-missing",
            capability="python_analysis_sandbox@v1",
            reason="invalid sandbox request",
        ),
    )

    assert result.status is ToolRunStatus.FAILED
    assert result.error_code == "EXECUTION_FAILED"


def test_gateway_blocks_cross_project_python_payload(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="data_analysis",
        agent_run_id="run-analysis",
        request=ToolRequest(
            request_id="request-python-cross-project",
            capability="python_analysis_sandbox@v1",
            input_payload={
                "request": {
                    "project_id": "project-b",
                    "script": "print('{}')",
                    "input_paths": [],
                    "output_schema_ref": "schema://AnalysisOutput",
                }
            },
            reason="cross-project sandbox request",
        ),
    )

    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"


def test_gateway_blocks_cross_project_uri_in_candidate_body(tmp_path: Path) -> None:
    gateway, _ = _gateway(tmp_path)
    result = gateway.execute(
        project_id="project-a",
        agent_id="paper_writing",
        agent_run_id="run-writing",
        request=ToolRequest(
            request_id="request-cross-project-uri",
            capability="manuscript_renderer_en@v1",
            input_payload={"graph_ref": "artifact-content://project-b/secret/1"},
            reason="candidate must remain project scoped",
        ),
    )

    assert result.status is ToolRunStatus.BLOCKED
    assert result.error_code == "PROJECT_SCOPE_VIOLATION"
