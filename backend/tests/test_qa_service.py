from __future__ import annotations

from pathlib import Path

from stem_sci.knowledge.models import (
    ContextMode,
    GraphCandidate,
    RetrievalMode,
    RetrievalSearchResponse,
    RetrievalTrace,
)
from stem_sci.knowledge.qa_models import QAAnswerRequest
from stem_sci.knowledge.qa_service import QuestionAnswerService


class FakeKnowledgeService:
    def __init__(self) -> None:
        self.search_calls: list[str] = []
        self.context_calls: list[str] = []
        self.search_modes: list[ContextMode] = []
        self.context_modes: list[str] = []

    def search(self, request):
        self.search_calls.append(request.query)
        self.search_modes.append(request.mode)
        from stem_sci.knowledge.models import RetrievalHitSummary

        hit = RetrievalHitSummary(
            canonical_chunk_id="chunk-1",
            canonical_paper_id="paper-1",
            source_filename="paper.pdf",
            paper_title="Physics Education Study",
            normalized_doi="10.1000/example",
            chunk_index=0,
            section_hint="Abstract",
            excerpt="The study reports improved conceptual understanding.",
            locator_status="UNRESOLVED",
            retrieval_modalities=["sparse"],
        )
        trace = RetrievalTrace(
            query_normalized=request.query,
            retrieval_mode=RetrievalMode.SPARSE_ONLY,
            corpus_id="physics_stem_v1",
            manifest_refs=["manifest:physics_stem_v1:test"],
            risk_flags=["dense_retrieval_unavailable"],
            dense_available=False,
            sparse_available=True,
            graph_available=False,
        )
        return RetrievalSearchResponse(
            project_id=request.project_id,
            corpus_id="physics_stem_v1",
            requested_mode=ContextMode.DISCOVERY,
            retrieval_status="DEGRADED",
            degraded_mode=RetrievalMode.SPARSE_ONLY,
            candidate_papers=[],
            chunk_hits=[hit],
            retrieval_trace=trace,
            risk_flags=["dense_retrieval_unavailable"],
            manifest_refs=trace.manifest_refs,
        )

    def build_context(self, **kwargs):
        self.context_calls.append(kwargs["query"])
        self.context_modes.append(kwargs["mode"])
        from stem_sci.context.models import ContextBundle

        return ContextBundle(
            context_id="ctx-test",
            project_id=kwargs["project_id"],
            task_ref=kwargs["task_ref"],
            query=kwargs["query"],
            evidence_refs=[],
            source_refs=[],
            unresolved_questions=[],
            risk_flags=[],
            verification_summary={},
            token_budget=kwargs["token_budget"],
            estimated_tokens=0,
            context_hash="a" * 64,
            generated_at="2026-08-20T00:00:00+00:00",
            context_mode="discovery",
            corpus_refs=["physics_stem_v1"],
            retrieval_strategy="hybrid",
        )


def test_qa_fallback_retrieves_cites_and_persists_memory(tmp_path: Path) -> None:
    knowledge = FakeKnowledgeService()
    service = QuestionAnswerService(
        knowledge_service=knowledge,
        storage_root=tmp_path,
    )

    response = service.answer(
        QAAnswerRequest(
            project_id="demo",
            question="What improves conceptual understanding?",
            conversation_id="conversation-1",
            allow_llm=False,
        )
    )

    assert response.answer_mode == "fallback"
    assert response.citations[0].canonical_chunk_id == "chunk-1"
    assert response.memory_ref is not None
    assert response.context_bundle_ref == "ctx-test"
    assert knowledge.search_calls
    assert knowledge.context_calls

    second = service.answer(
        QAAnswerRequest(
            project_id="demo",
            question="What did the previous study report?",
            conversation_id="conversation-1",
            allow_llm=False,
        )
    )
    assert "Physics Education Study" in second.answer
    assert len(knowledge.search_calls) == 2
    assert len(second.rewritten_query) > len(second.question)


def test_qa_propagates_formal_mode_to_retrieval_and_context(tmp_path: Path) -> None:
    knowledge = FakeKnowledgeService()
    service = QuestionAnswerService(
        knowledge_service=knowledge,
        storage_root=tmp_path,
    )

    service.answer(
        QAAnswerRequest(
            project_id="demo",
            question="Which evidence supports the study?",
            mode=ContextMode.FORMAL,
            allow_llm=False,
        )
    )

    assert knowledge.search_modes == [ContextMode.FORMAL]
    assert knowledge.context_modes == ["formal"]


def test_qa_graph_only_fallback_returns_exploratory_paper_candidates(tmp_path: Path) -> None:
    class GraphOnlyKnowledgeService(FakeKnowledgeService):
        def search(self, request):
            trace = RetrievalTrace(
                query_normalized=request.query,
                retrieval_mode=RetrievalMode.GRAPH_ONLY,
                corpus_id="physics_stem_v1",
                manifest_refs=["manifest:physics_stem_v1:test"],
                graph_candidates=[
                    GraphCandidate(
                        canonical_paper_id="paper-ai",
                        graph_paper_id="Generative AI in Physics Education",
                        navigation_score=1.0,
                        matched_facets=["Physics Education", "Instructional Scaffolding"],
                        supporting_edge_refs=["graph:paper-ai:0"],
                    )
                ],
                dense_available=False,
                sparse_available=False,
                graph_available=True,
            )
            return RetrievalSearchResponse(
                project_id=request.project_id,
                corpus_id="physics_stem_v1",
                requested_mode=ContextMode.DISCOVERY,
                retrieval_status="DEGRADED",
                degraded_mode=RetrievalMode.GRAPH_ONLY,
                candidate_papers=trace.graph_candidates,
                chunk_hits=[],
                retrieval_trace=trace,
                risk_flags=["graph_only_discovery"],
                manifest_refs=trace.manifest_refs,
            )

    service = QuestionAnswerService(
        knowledge_service=GraphOnlyKnowledgeService(),
        storage_root=tmp_path,
    )
    response = service.answer(
        QAAnswerRequest(project_id="demo", question="physics AI research", allow_llm=False)
    )

    assert "探索性论文候选" in response.answer
    assert "Generative AI in Physics Education" in response.answer
    assert "不能作为正式证据" in response.answer
    assert response.citations[0].source_type == "paper"
    assert response.confidence > 0
