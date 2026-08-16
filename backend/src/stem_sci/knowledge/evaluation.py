"""Offline retrieval evaluation primitives for a frozen, human-labelled gold set."""

from __future__ import annotations

from collections.abc import Callable
from math import log2

from pydantic import BaseModel, ConfigDict

from .models import RetrievalSearchRequest, RetrievalSearchResponse


class _GoldQuestion(BaseModel):
    """A minimal, already human-labelled gold-set question."""

    model_config = ConfigDict(extra="ignore")

    question_id: str
    language: str
    query: str
    relevant_paper_ids: list[str]
    strongly_relevant_chunk_ids: list[str]
    annotation_status: str


class _GoldSet(BaseModel):
    """Projection of the evaluation artifact used by the evaluator."""

    model_config = ConfigDict(extra="ignore")

    corpus_id: str
    status: str
    questions: list[_GoldQuestion]


class QueryMetric(BaseModel):
    """Per-question retrieval metrics for audit and later comparison."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    paper_recall_at_5: float
    chunk_hit_rate_at_5: float
    reciprocal_rank: float
    ndcg_at_10: float


class EvaluationReport(BaseModel):
    """Summary of a deterministic, label-backed evaluation run."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    evaluated_questions: int
    paper_recall_at_5: float
    chunk_hit_rate_at_5: float
    mean_reciprocal_rank: float
    mean_ndcg_at_10: float
    per_question: list[QueryMetric]


def evaluate_gold_set(
    gold_payload: str,
    search: Callable[[RetrievalSearchRequest], RetrievalSearchResponse],
    *,
    project_id: str = "evaluation",
) -> EvaluationReport:
    """Evaluate only a frozen, fully annotated gold set; templates are rejected."""

    gold = _GoldSet.model_validate_json(gold_payload)
    if gold.status != "FROZEN":
        raise ValueError("Retrieval Gold Set must be FROZEN before evaluation")
    if not gold.questions or any(question.annotation_status != "VERIFIED" for question in gold.questions):
        raise ValueError("Every evaluation question must be independently verified")
    metrics: list[QueryMetric] = []
    for question in gold.questions:
        response = search(
            RetrievalSearchRequest(
                project_id=project_id,
                corpus_ids=[gold.corpus_id],
                query=question.query,
                limit=10,
            )
        )
        ranked_papers = [hit.canonical_paper_id for hit in response.chunk_hits]
        ranked_chunks = [hit.canonical_chunk_id for hit in response.chunk_hits]
        relevant_papers = set(question.relevant_paper_ids)
        relevant_chunks = set(question.strongly_relevant_chunk_ids)
        paper_recall = _recall(ranked_papers[:5], relevant_papers)
        chunk_hit_rate = _recall(ranked_chunks[:5], relevant_chunks)
        first_rank = next((index for index, item in enumerate(ranked_papers, start=1) if item in relevant_papers), None)
        metrics.append(
            QueryMetric(
                question_id=question.question_id,
                paper_recall_at_5=paper_recall,
                chunk_hit_rate_at_5=chunk_hit_rate,
                reciprocal_rank=(0.0 if first_rank is None else 1 / first_rank),
                ndcg_at_10=_ndcg(ranked_chunks[:10], relevant_chunks),
            )
        )
    count = len(metrics)
    return EvaluationReport(
        corpus_id=gold.corpus_id,
        evaluated_questions=count,
        paper_recall_at_5=sum(metric.paper_recall_at_5 for metric in metrics) / count,
        chunk_hit_rate_at_5=sum(metric.chunk_hit_rate_at_5 for metric in metrics) / count,
        mean_reciprocal_rank=sum(metric.reciprocal_rank for metric in metrics) / count,
        mean_ndcg_at_10=sum(metric.ndcg_at_10 for metric in metrics) / count,
        per_question=metrics,
    )


def _recall(ranked: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked).intersection(relevant)) / len(relevant)


def _ndcg(ranked: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    dcg = sum(1 / log2(index + 1) for index, item in enumerate(ranked, start=1) if item in relevant)
    ideal = sum(1 / log2(index + 1) for index in range(1, min(len(relevant), len(ranked)) + 1))
    return 0.0 if ideal == 0 else dcg / ideal
