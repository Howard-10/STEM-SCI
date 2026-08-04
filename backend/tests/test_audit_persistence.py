from datetime import UTC, datetime

from stem_sci.artifacts.artifact_store import SQLiteArtifactStore
from stem_sci.artifacts.models import ArtifactRef
from stem_sci.controller.policy.route_decision import RouteDecision
from stem_sci.controller.policy.route_store import SQLiteRouteDecisionStore
from stem_sci.core.enums import DecisionScope, ProjectStage
from stem_sci.provenance.agent_run_store import SQLiteAgentRunStore
from stem_sci.provenance.models import AgentRunRecord


def test_sqlite_audit_stores_restore_artifact_agent_run_and_route(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    created_at = datetime.now(UTC)
    artifact = ArtifactRef(
        artifact_id="candidate-1",
        project_id="audit-demo",
        artifact_type="ResearchContractCandidate",
        version=1,
        content_uri="candidate://mentor/audit-demo/ResearchContractCandidate",
        sha256="a" * 64,
        created_at=created_at,
        created_by="mentor_planning",
    )
    agent_run = AgentRunRecord(
        agent_run_id="agent-run-1",
        project_id="audit-demo",
        agent_id="mentor_planning",
        agent_version="phase1-scaffold",
        prompt_template_version="planner-v1",
        input_artifact_refs=["context://initial"],
        output_artifact_refs=[artifact.content_uri],
        tool_run_refs=["operator-run-1"],
        route_decision_ref="route-1",
        started_at=created_at,
        finished_at=created_at,
    )
    route = RouteDecision(
        decision_id="route-1",
        project_id="audit-demo",
        current_stage=ProjectStage.INTAKE,
        selected_route="mentor_planning",
        reason="scope required",
        decision_scope=DecisionScope.PROJECT,
        created_at=created_at,
    )

    artifact_store = SQLiteArtifactStore(database)
    agent_store = SQLiteAgentRunStore(database)
    route_store = SQLiteRouteDecisionStore(database)
    artifact_store.put(artifact)
    agent_store.put(agent_run)
    route_store.put(route)

    assert SQLiteArtifactStore(database).get("audit-demo", "candidate-1") == artifact
    assert SQLiteAgentRunStore(database).get("audit-demo", "agent-run-1") == agent_run
    assert SQLiteRouteDecisionStore(database).get("audit-demo", "route-1") == route


def test_controller_writes_audit_records_for_planning_run(tmp_path) -> None:
    from stem_sci.artifacts.artifact_store import SQLiteArtifactStore
    from stem_sci.controller import (
        PlanningRequest,
        ResearchController,
    )
    from stem_sci.provenance.agent_run_store import SQLiteAgentRunStore

    database = tmp_path / "workflow.db"
    controller = ResearchController(
        artifact_store=SQLiteArtifactStore(database),
        agent_run_store=SQLiteAgentRunStore(database),
        route_store=SQLiteRouteDecisionStore(database),
    )
    result = controller.start_planning(
        PlanningRequest(project_id="controller-audit", research_intent="scope", run_id="audit-run")
    )

    artifact_store = SQLiteArtifactStore(database)
    agent_store = SQLiteAgentRunStore(database)
    route_store = SQLiteRouteDecisionStore(database)
    assert artifact_store.list_project("controller-audit")
    assert agent_store.get("controller-audit", result.agent_result.agent_run_id) is not None
    assert route_store.get("controller-audit", result.route_decision.decision_id) is not None
