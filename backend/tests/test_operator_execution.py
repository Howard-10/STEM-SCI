from types import SimpleNamespace

from stem_sci.agents import ToolRequest
from stem_sci.artifacts.artifact_store import InMemoryArtifactStore
from stem_sci.artifacts.content_store import InMemoryArtifactContentStore
from stem_sci.artifacts.execution_store import SQLiteExecutionStore
from stem_sci.context.models import (
    ContextBundle,
    EvidenceRef,
    SourceLocation,
    VerificationStatus,
)
from stem_sci.controller import OperatorExecutor, PlanningRequest, ResearchController
from stem_sci.core.enums import ProjectStage, RunStatus
from stem_sci.knowledge.models import (
    RetrievalHitSummary,
    RetrievalMode,
    RetrievalSearchResponse,
    RetrievalTrace,
)
from stem_sci.operators.knowledge import KnowledgeOperatorRuntime
from stem_sci.operators.registry import OperatorRegistry


def test_registered_but_unimplemented_operator_is_recorded_as_blocked() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())

    runs = executor.execute_tool_requests(
        project_id="operator-demo",
        agent_run_id="agent-run-1",
        tool_requests=["request://literature_search"],
    )

    assert len(runs) == 1
    assert runs[0].operator_id == "literature_search"
    assert runs[0].status is RunStatus.BLOCKED
    assert runs[0].error_ref == "error://operator/literature_search/unsupported"


def test_unknown_operator_request_is_recorded_as_failed() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())

    runs = executor.execute_tool_requests(
        project_id="operator-demo",
        agent_run_id="agent-run-2",
        tool_requests=["request://does_not_exist"],
    )

    assert runs[0].status is RunStatus.FAILED
    assert runs[0].error_ref == "error://operator/does_not_exist/unknown"


def test_operator_executor_accepts_structured_tool_request() -> None:
    executor = OperatorExecutor(OperatorRegistry.default())
    run = executor.execute(
        "operator-structured-demo",
        ToolRequest(
            request_id="structured-tool-1",
            capability="literature_search",
            input_refs=["artifact://scope/1"],
            required_output_types=["EvidenceSet"],
            reason="Need evidence.",
        ),
    )

    assert run.request_ref == "structured-tool-1"
    assert run.input_artifact_refs == ["artifact://scope/1"]


def test_sqlite_execution_store_restores_operator_run(tmp_path) -> None:
    database = tmp_path / "workflow.db"
    executor = OperatorExecutor(
        OperatorRegistry.default(), SQLiteExecutionStore(database)
    )
    run = executor.execute_tool_requests(
        project_id="operator-persist-demo",
        agent_run_id="agent-run-3",
        tool_requests=["request://literature_search"],
    )[0]

    restored = SQLiteExecutionStore(database).get("operator-persist-demo", run.operator_run_id)

    assert restored == run


def test_controller_merges_operator_run_refs_and_execution_risk() -> None:
    controller = ResearchController(
        operator_executor=OperatorExecutor(OperatorRegistry.default())
    )
    first = controller.start_planning(
        PlanningRequest(
            project_id="operator-controller-demo",
            research_intent="scope",
            run_id="operator-planning-1",
        )
    )
    scoped = controller.approve_planning(first.workflow_state, first.approval_request)
    next_run = controller.run_next("operator-controller-demo")

    assert scoped.current_stage is ProjectStage.SCOPED
    state = next_run.workflow_state.research_state
    assert state is not None
    assert state.execution_run_refs
    assert "OPERATOR_EXECUTION_UNAVAILABLE" in state.risk_flags


class FakeKnowledgeService:
    def search(self, request):
        hit = RetrievalHitSummary(
            canonical_chunk_id="chunk-1",
            canonical_paper_id="paper-1",
            source_filename="paper-1.pdf",
            paper_title="Physics paper",
            chunk_index=0,
            section_hint="Body",
            excerpt="Retrieved excerpt for development.",
            dense_rank=1,
            sparse_rank=1,
            rrf_score=0.03,
            locator_status="UNRESOLVED",
            retrieval_modalities=["dense", "sparse"],
        )
        return RetrievalSearchResponse(
            project_id=request.project_id,
            corpus_id="physics_stem_v1",
            requested_mode=request.mode,
            retrieval_status="READY",
            candidate_papers=[],
            chunk_hits=[hit],
            retrieval_trace=RetrievalTrace(
                query_normalized=request.query,
                retrieval_mode=RetrievalMode.HYBRID_DENSE_SPARSE,
                corpus_id="physics_stem_v1",
                manifest_refs=["manifest:physics_stem_v1:1.0.0"],
                dense_available=True,
                sparse_available=True,
                graph_available=False,
            ),
            risk_flags=[],
            manifest_refs=["manifest:physics_stem_v1:1.0.0"],
        )

    def readiness(self, _corpus_id):
        return SimpleNamespace(formal_evidence_ready=False)


def _context_bundle() -> ContextBundle:
    evidence = EvidenceRef(
        evidence_id="evidence-1",
        project_id="operator-runtime-demo",
        source_id="source-1",
        chunk_id="chunk-1",
        excerpt="Retrieved excerpt.",
        location=SourceLocation(chunk_index=0, char_start=0, char_end=18),
        verification_status=VerificationStatus.MODEL_GENERATED_UNVERIFIED,
        canonical_paper_id="paper-1",
        canonical_chunk_id="chunk-1",
    )
    return ContextBundle(
        context_id="context-1",
        project_id="operator-runtime-demo",
        task_ref="evidence",
        query="physics",
        evidence_refs=[evidence],
        source_refs=["source-1"],
        risk_flags=["UNVERIFIED_FORMAL_EVIDENCE_ENABLED"],
        verification_summary={"model_generated_unverified": 1},
        token_budget=500,
        estimated_tokens=10,
        context_hash="a" * 64,
        generated_at="2026-08-21T00:00:00Z",
        context_mode="formal",
    )


def test_knowledge_operators_execute_and_persist_outputs() -> None:
    artifact_store = InMemoryArtifactStore()
    content_store = InMemoryArtifactContentStore()
    runtime = KnowledgeOperatorRuntime(
        FakeKnowledgeService(),
        artifact_store=artifact_store,
        artifact_content_store=content_store,
    )
    executor = OperatorExecutor(
        OperatorRegistry.default(),
        handlers=runtime.handlers(),
    )

    search = executor.execute(
        "operator-runtime-demo",
        ToolRequest(
            request_id="search-1",
            capability="literature_search",
            reason="retrieve papers",
        ),
        query="physics",
        agent_run_id="agent-1",
    )
    screening = executor.execute(
        "operator-runtime-demo",
        ToolRequest(
            request_id="screen-1",
            capability="paper_screening",
            reason="screen retrieved papers",
        ),
        query="physics",
        context_bundle=_context_bundle(),
        agent_run_id="agent-1",
    )
    extraction = executor.execute(
        "operator-runtime-demo",
        ToolRequest(
            request_id="extract-1",
            capability="paper_extraction",
            reason="extract paper cards",
        ),
        query="physics",
        context_bundle=_context_bundle(),
        agent_run_id="agent-1",
    )
    verification = executor.execute(
        "operator-runtime-demo",
        ToolRequest(
            request_id="verify-1",
            capability="source_verification",
            reason="verify source traceability",
        ),
        query="physics",
        context_bundle=_context_bundle(),
        agent_run_id="agent-1",
    )

    assert search.status is RunStatus.SUCCEEDED
    assert screening.status is RunStatus.SUCCEEDED
    assert extraction.status is RunStatus.SUCCEEDED
    assert verification.status is RunStatus.NEEDS_REVIEW
    assert all(
        run.output_artifact_refs
        for run in (search, screening, extraction, verification)
    )
    assert {
        item.artifact_type
        for item in artifact_store.list_project("operator-runtime-demo")
    } == {"EvidenceSet", "ScreenedPaperSet", "PaperCard", "VerifiedEvidenceRef"}


def test_controller_uses_real_literature_operator_without_unavailable_risk() -> None:
    runtime = KnowledgeOperatorRuntime(
        FakeKnowledgeService(),
        artifact_store=InMemoryArtifactStore(),
        artifact_content_store=InMemoryArtifactContentStore(),
    )
    controller = ResearchController(
        operator_executor=OperatorExecutor(
            OperatorRegistry.default(),
            handlers=runtime.handlers(),
        )
    )

    run = controller.start_planning(
        PlanningRequest(
            project_id="operator-runtime-controller",
            research_intent="physics",
            run_id="operator-runtime-planning",
        )
    )

    state = run.workflow_state.research_state
    assert state is not None
    assert "OPERATOR_EXECUTION_UNAVAILABLE" not in state.risk_flags
    assert state.execution_run_refs
    assert any(
        ref.startswith("artifact-content://operator-runtime-controller/")
        for ref in state.artifact_refs
    )
