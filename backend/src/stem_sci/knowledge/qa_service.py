"""End-to-end conversational QA over the shared knowledge corpus."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from stem_sci.agents.runtime import GPTProvider, StructuredGenerator
from stem_sci.context.models import ContextBundle

from .models import ContextMode, RetrievalSearchRequest, RetrievalSearchResponse
from .normalization import expanded_query, normalize_doi, normalize_text
from .qa_memory import ConversationMemoryStore
from .qa_models import (
    ConversationSummary,
    MemoryTurn,
    QAAnswerRecord,
    QAAnswerRequest,
    QAAnswerResponse,
    QAReference,
    QARouteDecision,
    QAWorkflowAction,
)
from .service import HybridKnowledgeService
from .qa_tools import (
    WORKFLOW_TOOL_NAMES,
    QAToolExecutor,
    route_for_tool,
    tool_definitions,
    tool_reason,
)


class _AnswerDraft(BaseModel):
    """Strict JSON contract requested from the conversational model."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    citation_indices: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    needs_follow_up: bool = False
    follow_up_question: str | None = None


class QuestionAnswerService:
    """Compose rewrite, retrieval, synthesis, and memory into one API operation."""

    def __init__(
        self,
        *,
        knowledge_service: HybridKnowledgeService,
        storage_root: Path,
        provider: GPTProvider | None = None,
        model: str | None = None,
        workflow_controller: Any | None = None,
        artifact_store: Any | None = None,
        prompt_version: str = "qa-v1",
        max_retries: int = 1,
    ) -> None:
        self._knowledge_service = knowledge_service
        self._memory_store = ConversationMemoryStore(storage_root / "memory")
        self._provider = provider
        self._generator = (
            StructuredGenerator(provider, max_retries=max_retries) if provider else None
        )
        self._tool_executor = QAToolExecutor(
            knowledge_service,
            workflow_controller=workflow_controller,
            artifact_store=artifact_store,
        )
        self._model = model or (provider.default_model if provider else None)
        self._prompt_version = prompt_version

    def answer(self, request: QAAnswerRequest) -> QAAnswerResponse:
        conversation_id = request.conversation_id or f"conv_{uuid4().hex}"
        history = self._memory_store.recent_turns(
            conversation_id,
            limit=4,
            project_id=request.project_id,
        )
        rewritten_query = self._rewrite_query(request.question, history)
        route = self._route(request.question, rewritten_query, history)

        retrieval = self._knowledge_service.search(
            RetrievalSearchRequest(
                project_id=request.project_id,
                corpus_ids=["physics_stem_v1"],
                query=rewritten_query,
                mode=request.mode,
                limit=request.top_k,
            )
        )
        context_bundle = self._knowledge_service.build_context(
            project_id=request.project_id,
            task_ref=request.context_bundle_ref or conversation_id,
            query=rewritten_query,
            token_budget=request.token_budget,
            mode=request.mode.value,
        )
        citations = self._build_citations(retrieval)
        allow_llm = (
            request.allow_llm
            and self._generator is not None
            and self._model is not None
        )
        agentic_result = self._agentic_synthesize(
            request=request,
            question=request.question,
            rewritten_query=rewritten_query,
            route=route,
            retrieval=retrieval,
            context_bundle=context_bundle,
            citations=citations,
            history=history,
            allow_llm=allow_llm,
            mode=request.mode,
        )
        if agentic_result is not None:
            (
                answer_record,
                route,
                retrieval,
                citations,
                tool_calls,
                context_bundle,
                workflow_action,
            ) = agentic_result
            answer_mode: Literal["llm", "fallback"] = "llm"
        else:
            answer_record, answer_mode = self._synthesize(
                question=request.question,
                rewritten_query=rewritten_query,
                route=route,
                retrieval=retrieval,
                context_bundle=context_bundle,
                citations=citations,
                history=history,
                allow_llm=allow_llm,
            )
            tool_calls = []
            workflow_action = None
        selected_citations = self._select_citations(
            citations, answer_record.citation_indices
        )
        trace_ref = self._trace_ref(retrieval)
        memory_turn = self._memory_store.append_turn(
            conversation_id=conversation_id,
            project_id=request.project_id,
            question=request.question,
            rewritten_query=rewritten_query,
            answer=answer_record.answer,
            route=route.route,
            citations=selected_citations,
            retrieval_trace_ref=trace_ref,
        )
        return QAAnswerResponse(
            project_id=request.project_id,
            conversation_id=conversation_id,
            question=request.question,
            rewritten_query=rewritten_query,
            route=route,
            answer=answer_record.answer,
            citations=selected_citations,
            retrieval_status=retrieval.retrieval_status,
            retrieval_trace_ref=trace_ref,
            context_bundle_ref=context_bundle.context_id,
            memory_ref=memory_turn.memory_id,
            risk_flags=sorted(
                set([*retrieval.risk_flags, *context_bundle.risk_flags])
            ),
            answer_mode=answer_mode,
            confidence=answer_record.confidence,
            needs_follow_up=answer_record.needs_follow_up,
            follow_up_question=answer_record.follow_up_question,
            tool_calls=tool_calls,
            workflow_action=workflow_action,
        )

    def list_conversations(
        self,
        project_id: str,
        *,
        limit: int = 50,
    ) -> list[ConversationSummary]:
        return self._memory_store.list_conversations(project_id, limit=limit)

    def conversation_turns(
        self,
        project_id: str,
        conversation_id: str,
        *,
        limit: int = 100,
    ) -> list[MemoryTurn]:
        return self._memory_store.conversation_turns(
            project_id=project_id,
            conversation_id=conversation_id,
            limit=limit,
        )

    def _rewrite_query(self, question: str, history: list[MemoryTurn]) -> str:
        """Use the existing transparent rewrite and add bounded conversation context."""

        base = expanded_query(question)
        if not history:
            return base
        history_hint = " ".join(
            normalize_text(f"{turn.question} {turn.answer}")[:240]
            for turn in history[-2:]
        )
        return f"{base} {history_hint}".strip()

    def _route(
        self,
        question: str,
        rewritten_query: str,
        history: list[MemoryTurn],
    ) -> QARouteDecision:
        """Choose a safe coarse route; retrieval remains hybrid by default."""

        normalized = normalize_text(question)
        if any(
            marker in normalized
            for marker in ("doi", "论文编号", "这篇论文", "paper id")
        ):
            return QARouteDecision(
                route="paper_lookup",
                reason="问题明显指向单篇论文定位",
            )
        if any(
            marker in normalized
            for marker in (
                "agent",
                "智能体",
                "workflow",
                "项目",
                "写作",
                "审稿",
                "设计",
                "分析",
            )
        ):
            return QARouteDecision(
                route="workflow_agent",
                reason="问题更像研究工作流任务",
                recommended_agent=self._agent_hint(normalized),
            )
        if history:
            return QARouteDecision(
                route="hybrid_search",
                reason="结合当前会话记忆继续检索和回答",
            )
        if "图谱" in rewritten_query or "三元组" in rewritten_query:
            return QARouteDecision(
                route="hybrid_search",
                reason="需要图谱导航和全文证据共同参与",
            )
        return QARouteDecision(
            route="hybrid_search",
            reason="默认使用图谱引导的向量+稀疏混合检索",
        )

    @staticmethod
    def _agent_hint(question: str) -> str:
        if any(marker in question for marker in ("写作", "论文", "manuscript")):
            return "PaperWritingAgent"
        if any(marker in question for marker in ("审稿", "review", "批判")):
            return "IndependentReviewAgent"
        if any(marker in question for marker in ("设计", "方案", "实验")):
            return "ResearchDesignAgent"
        if any(marker in question for marker in ("分析", "统计", "data", "结果")):
            return "DataAnalysisAgent"
        if any(marker in question for marker in ("证据", "evidence", "文献")):
            return "EvidenceReviewAgent"
        return "MentorPlanningAgent"

    def _agentic_synthesize(
        self,
        *,
        request: QAAnswerRequest,
        question: str,
        rewritten_query: str,
        route: QARouteDecision,
        retrieval: RetrievalSearchResponse,
        context_bundle: ContextBundle,
        citations: list[QAReference],
        history: list[MemoryTurn],
        allow_llm: bool,
        mode: ContextMode,
    ) -> tuple[
        QAAnswerRecord,
        QARouteDecision,
        RetrievalSearchResponse,
        list[QAReference],
        list[str],
        ContextBundle,
        QAWorkflowAction | None,
    ] | None:
        """Let the model choose bounded retrieval or workflow tools."""

        if (
            not allow_llm
            or self._provider is None
            or not hasattr(self._provider, "complete")
            or not self._model
        ):
            return None
        try:
            first = self._provider.complete(
                messages=[
                    {
                        "role": "system",
                        "content": self._tool_router_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": self._tool_router_user_prompt(
                            question,
                            rewritten_query,
                            route,
                            retrieval,
                            history,
                        ),
                    },
                ],
                model=self._model,
                tools=tool_definitions(),
                tool_choice="auto",
            )
            if not first.tool_calls:
                return None

            calls = list(first.tool_calls[:3])
            workflow_calls = [call for call in calls if call.name in WORKFLOW_TOOL_NAMES]
            if workflow_calls:
                # A single turn may perform at most one Controller workflow action.
                calls = workflow_calls[:1]
            selected_tool = calls[0] if calls else first.tool_calls[0]
            assistant_message = dict(first.message)
            if workflow_calls:
                raw_tool_calls = assistant_message.get("tool_calls")
                if isinstance(raw_tool_calls, list):
                    assistant_message["tool_calls"] = [
                        item
                        for item in raw_tool_calls
                        if isinstance(item, Mapping)
                        and item.get("id") == selected_tool.call_id
                    ]

            messages: list[Mapping[str, Any]] = [
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(
                        question,
                        rewritten_query,
                        route,
                        retrieval,
                        context_bundle,
                        citations,
                        history,
                    ),
                },
                assistant_message,
            ]
            tool_names: list[str] = []
            workflow_action: QAWorkflowAction | None = None
            active_retrieval = retrieval
            active_citations = citations
            active_context_bundle = context_bundle
            for call in calls:
                tool_names.append(call.name)
                result = self._tool_executor.execute(
                    name=call.name,
                    arguments=call.arguments,
                    project_id=request.project_id,
                    default_query=rewritten_query,
                    mode=mode,
                )
                workflow_payload = result.get("workflow_action")
                if isinstance(workflow_payload, Mapping):
                    try:
                        workflow_action = QAWorkflowAction.model_validate(workflow_payload)
                    except ValueError:
                        workflow_action = None
                retrieval_payload = result.get("retrieval_response")
                if isinstance(retrieval_payload, Mapping):
                    try:
                        active_retrieval = RetrievalSearchResponse.model_validate(
                            retrieval_payload
                        )
                        active_citations = self._build_citations(active_retrieval)
                        tool_query = str(
                            call.arguments.get("query") or rewritten_query
                        ).strip()
                        active_context_bundle = self._knowledge_service.build_context(
                            project_id=request.project_id,
                            task_ref=context_bundle.task_ref,
                            query=tool_query,
                            token_budget=context_bundle.token_budget,
                            mode=mode.value,
                        )
                    except ValueError:
                        active_retrieval = retrieval
                        active_citations = citations
                        active_context_bundle = context_bundle
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "name": call.name,
                        "content": self._json_text(result),
                    }
                )

            messages.append(
                {
                    "role": "user",
                    "content": self._user_prompt(
                        question,
                        rewritten_query,
                        QARouteDecision(
                            route=route_for_tool(selected_tool.name),
                            reason=tool_reason(selected_tool.name),
                            recommended_agent=route.recommended_agent,
                        ),
                        active_retrieval,
                        active_context_bundle,
                        active_citations,
                        history,
                    ),
                }
            )
            try:
                final = self._provider.complete(
                    messages=messages,
                    model=self._model,
                    response_model=_AnswerDraft,
                )
                if not final.content:
                    raise ValueError("LLM returned no final answer")
                parsed = _AnswerDraft.model_validate_json(final.content)
            except Exception:
                if workflow_action is None:
                    raise
                parsed = _AnswerDraft(
                    answer=workflow_action.message,
                    citation_indices=[],
                    confidence=0.9,
                    needs_follow_up=workflow_action.confirmation_required,
                    follow_up_question=(
                        "请在工作流页面确认批准或退回当前候选。"
                        if workflow_action.confirmation_required
                        else None
                    ),
                )
            public_route = route_for_tool(selected_tool.name)
            recommended_agent = (
                str(selected_tool.arguments.get("agent"))
                if selected_tool.name == "workflow_agent"
                and selected_tool.arguments.get("agent")
                else route.recommended_agent
            )
            return (
                QAAnswerRecord(
                    answer=parsed.answer,
                    citation_indices=self._clamp_indices(
                        parsed.citation_indices,
                        len(active_citations),
                    ),
                    confidence=parsed.confidence,
                    needs_follow_up=parsed.needs_follow_up,
                    follow_up_question=parsed.follow_up_question,
                ),
                QARouteDecision(
                    route=public_route,
                    reason=tool_reason(selected_tool.name),
                    recommended_agent=recommended_agent,
                ),
                active_retrieval,
                active_citations,
                tool_names,
                active_context_bundle,
                workflow_action,
            )
        except Exception:
            # Tool routing is an enhancement; deterministic retrieval and the
            # existing structured synthesis remain the availability baseline.
            return None

    @staticmethod
    def _json_text(value: Mapping[str, Any]) -> str:
        import json

        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _tool_router_system_prompt() -> str:
        return (
            "You are the STEM-SCI research router. Select the minimum bounded "
            "retrieval or workflow tool needed for the user's request. Use "
            "hybrid_search for most "
            "research questions, paper_lookup for a specific paper, graph_search "
            "for relationship discovery, vector_search for textual evidence, "
            "start_research_workflow only when the user explicitly asks to create "
            "a project, get_workflow_status for progress questions, "
            "run_next_workflow_agent only when the user explicitly asks to continue, "
            "get_workflow_artifacts to inspect candidates, "
            "prepare_workflow_approval to show a pending approval, and "
            "workflow_agent only for proposal-only Agent recommendations. "
            "external_paper_search only when the local corpus is insufficient. "
            "Never invent tool results. Never approve, reject, freeze data, execute "
            "statistics, or release a project from the conversational tool layer."
        )

    @staticmethod
    def _tool_router_user_prompt(
        question: str,
        rewritten_query: str,
        route: QARouteDecision,
        retrieval: RetrievalSearchResponse,
        history: list[MemoryTurn],
    ) -> str:
        recent = "\n".join(
            f"- {turn.question}: {turn.answer[:180]}" for turn in history[-2:]
        )
        return (
            f"Question: {question}\n"
            f"Rewritten query: {rewritten_query}\n"
            f"Rule hint: {route.route} ({route.reason})\n"
            f"Baseline retrieval status: {retrieval.retrieval_status}\n"
            f"Recent memory:\n{recent or '- none'}\n"
            "Choose the minimum tool calls needed to answer safely."
        )

    def _synthesize(
        self,
        *,
        question: str,
        rewritten_query: str,
        route: QARouteDecision,
        retrieval: RetrievalSearchResponse,
        context_bundle: ContextBundle,
        citations: list[QAReference],
        history: list[MemoryTurn],
        allow_llm: bool,
    ) -> tuple[QAAnswerRecord, Literal["llm", "fallback"]]:
        if allow_llm and self._generator is not None and self._model:
            try:
                result = self._generator.generate(
                    system_prompt=self._system_prompt(),
                    user_prompt=self._user_prompt(
                        question,
                        rewritten_query,
                        route,
                        retrieval,
                        context_bundle,
                        citations,
                        history,
                    ),
                    response_model=_AnswerDraft,
                    model=self._model,
                    prompt_version=self._prompt_version,
                )
                parsed = _AnswerDraft.model_validate(result.parsed_output)
                return (
                    QAAnswerRecord(
                        answer=parsed.answer,
                        citation_indices=self._clamp_indices(
                            parsed.citation_indices, len(citations)
                        ),
                        confidence=parsed.confidence,
                        needs_follow_up=parsed.needs_follow_up,
                        follow_up_question=parsed.follow_up_question,
                    ),
                    "llm",
                )
            except Exception:
                # Retrieval should remain usable when a provider rejects a request.
                pass
        return self._fallback_answer(question, retrieval, citations), "fallback"

    @staticmethod
    def _fallback_answer(
        question: str,
        retrieval: RetrievalSearchResponse,
        citations: list[QAReference],
    ) -> QAAnswerRecord:
        if not retrieval.chunk_hits and retrieval.candidate_papers:
            candidates = retrieval.candidate_papers[:3]
            lines = [
                f"- {candidate.graph_paper_id}（匹配方向：{'、'.join(candidate.matched_facets[:3]) or '相关主题'}）"
                for candidate in candidates
            ]
            return QAAnswerRecord(
                answer=(
                    "当前全文资源尚未挂载，以下是基于知识图谱的探索性论文候选：\n"
                    + "\n".join(lines)
                    + "\n\n这些候选只能用于确定研究方向，不能作为正式证据；补入论文 PDF 和向量索引后再进行原文核验。"
                ),
                citation_indices=list(range(1, min(3, len(citations)) + 1)),
                confidence=0.25,
                needs_follow_up=True,
                follow_up_question="请补入对应论文原文，或继续限定研究对象、变量和时间范围。",
            )
        if not retrieval.chunk_hits:
            return QAAnswerRecord(
                answer=f"当前知识库没有找到足够证据回答：{question}",
                citation_indices=[],
                confidence=0.0,
                needs_follow_up=True,
                follow_up_question="请补充论文题目、研究对象或更具体的关键词。",
            )
        lines = [
            f"- {hit.paper_title}：{hit.excerpt}"
            for hit in retrieval.chunk_hits[:3]
        ]
        return QAAnswerRecord(
            answer="基于当前检索到的证据，相关信息如下：\n" + "\n".join(lines),
            citation_indices=list(range(1, min(3, len(citations)) + 1)),
            confidence=0.55,
        )

    @staticmethod
    def _build_citations(
        retrieval: RetrievalSearchResponse,
    ) -> list[QAReference]:
        citations: list[QAReference] = []
        for hit in retrieval.chunk_hits:
            citations.append(
                QAReference(
                    paper_title=hit.paper_title,
                    source_filename=hit.source_filename,
                    canonical_paper_id=hit.canonical_paper_id,
                    canonical_chunk_id=hit.canonical_chunk_id,
                    chunk_index=hit.chunk_index,
                    excerpt=hit.excerpt,
                    normalized_doi=normalize_doi(hit.normalized_doi),
                    pdf_relative_path=hit.pdf_relative_path,
                )
            )
        for candidate in retrieval.candidate_papers:
            citations.append(
                QAReference(
                    paper_title=candidate.graph_paper_id,
                    source_filename=candidate.graph_paper_id,
                    canonical_paper_id=candidate.canonical_paper_id,
                    canonical_chunk_id=(
                        candidate.supporting_edge_refs[0]
                        if candidate.supporting_edge_refs
                        else candidate.canonical_paper_id
                    ),
                    chunk_index=0,
                    excerpt="图谱导航候选论文，不能单独作为正式证据。",
                    source_type="paper",
                )
            )
        return citations

    @staticmethod
    def _select_citations(
        citations: list[QAReference],
        indices: list[int],
    ) -> list[QAReference]:
        if not indices:
            return citations[: min(3, len(citations))]
        selected = [
            citations[index - 1]
            for index in indices
            if 1 <= index <= len(citations)
        ]
        return selected or citations[: min(3, len(citations))]

    @staticmethod
    def _clamp_indices(indices: list[int], size: int) -> list[int]:
        return sorted({index for index in indices if 1 <= index <= size})[:5]

    @staticmethod
    def _trace_ref(retrieval: RetrievalSearchResponse) -> str:
        digest = hashlib.sha256(
            retrieval.retrieval_trace.query_normalized.encode("utf-8")
        ).hexdigest()[:16]
        return f"retrieval://{retrieval.corpus_id}/{digest}"

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are the STEM-SCI evidence assistant. Answer only from the supplied "
            "retrieved context. Never invent findings. Graph candidates are navigation "
            "hints, not formal evidence. Cite usable sources with 1-based citation "
            "indices. If evidence is insufficient, state that explicitly."
        )

    @staticmethod
    def _user_prompt(
        question: str,
        rewritten_query: str,
        route: QARouteDecision,
        retrieval: RetrievalSearchResponse,
        context_bundle: ContextBundle,
        citations: list[QAReference],
        history: list[MemoryTurn],
    ) -> str:
        context = "\n".join(
            f"[{index}] {item.paper_title} | {item.source_filename} | "
            f"chunk {item.chunk_index}: {item.excerpt}"
            for index, item in enumerate(citations[:8], start=1)
        )
        recent = "\n".join(
            f"- 问题：{turn.question}\n  回答：{turn.answer[:240]}"
            for turn in history[-3:]
        )
        bundle_evidence = "\n".join(
            f"- {item.evidence_id}: {item.excerpt}"
            for item in context_bundle.evidence_refs[:8]
        )
        return (
            f"用户问题：{question}\n"
            f"改写查询：{rewritten_query}\n"
            f"检索路线：{route.route}\n"
            f"路线说明：{route.reason}\n"
            f"检索状态：{retrieval.retrieval_status}\n"
            f"ContextBundle：{context_bundle.context_id}\n"
            f"历史对话：\n{recent or '- 无'}\n"
            f"上下文证据：\n{bundle_evidence or '- 无'}\n"
            f"证据：\n{context or '- 无'}\n"
            "请返回 JSON：answer、citation_indices、confidence、"
            "needs_follow_up、follow_up_question。"
        )
