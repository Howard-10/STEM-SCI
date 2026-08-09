"""RAG 主编排器 —— 串联 路由 → 检索 → 合成 全流程.

使用方式:
    pipeline = RAGPipeline()
    result = pipeline.answer("项目式学习对物理概念理解有什么效果？")
    print(result.answer)
    for c in result.citations:
        print(f"[{c.source_type}] {c.paper_title}")

也可以分步调用:
    decision = pipeline.route(question)
    data = pipeline.retrieve(decision)
    answer = pipeline.synthesize(question, data)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .config import LLMConfig
from .router import Router, RouteDecision
from .synthesizer import Synthesizer, SynthesisResult, Citation
from .tool_registry import ToolRegistry, create_default_registry
from .retriever import vector_search, graph_query, paper_lookup, hybrid_search


# ===========================================================================
# 顶层结果
# ===========================================================================


@dataclass
class RAGResponse:
    """RAG 编排器完整返回."""

    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    route_decision: RouteDecision | None = None
    retrieval_data: dict | None = None
    elapsed_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": [
                {
                    "paper_title": c.paper_title,
                    "doi": c.doi,
                    "year": c.year,
                    "evidence": c.evidence[:200],
                    "source_type": c.source_type,
                }
                for c in self.citations
            ],
            "route": {
                "tool": self.route_decision.tool_name if self.route_decision else "",
                "reasoning": self.route_decision.reasoning if self.route_decision else "",
                "method": self.route_decision.method if self.route_decision else "",
            },
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def __repr__(self) -> str:
        return (
            f"RAGResponse(route={self.route_decision.tool_name if self.route_decision else '?'}, "
            f"citations={len(self.citations)}, {self.elapsed_ms:.0f}ms)"
        )


# ===========================================================================
# RAGPipeline
# ===========================================================================


class RAGPipeline:
    """RAG 检索编排器.

    串联路由决策 → 检索执行 → 答案合成。
    后续可通过 registry 注册队友的 6 个 Agent。

    参数:
        config: LLM 配置，默认从环境变量读取
        project_id: Neo4j 项目 ID
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        project_id: str = "stem-sci",
    ) -> None:
        self.config = config or LLMConfig.from_env()
        self.project_id = project_id

        # 工具注册表（兼容 LLM function-calling 可能传的不同参数名）
        self.registry = create_default_registry(
            vector_search_fn=lambda **kw: vector_search(
                query=kw.get("query") or kw.get("keyword", ""),
                top_k=kw.get("top_k", 5),
            ),
            graph_query_fn=lambda **kw: graph_query(
                project_id=project_id,
                keyword=kw.get("keyword") or kw.get("query", ""),
                entity_type=kw.get("entity_type", ""),
                relation_type=kw.get("relation_type", ""),
                limit=kw.get("limit", 15),
            ),
            paper_lookup_fn=lambda **kw: paper_lookup(
                project_id=project_id,
                paper_id=kw.get("paper_id") or kw.get("query") or kw.get("keyword", ""),
            ),
            hybrid_search_fn=lambda **kw: hybrid_search(
                query=kw.get("query") or kw.get("keyword", ""),
                keyword=kw.get("keyword") or kw.get("query", ""),
                top_k=kw.get("top_k", 5),
                graph_limit=kw.get("limit", 10),
            ),
        )

        # 子模块
        self.router = Router(self.config, self.registry)
        self.synthesizer = Synthesizer(self.config)

    # ------------------------------------------------------------------
    # 分步接口
    # ------------------------------------------------------------------

    def route(self, question: str) -> RouteDecision:
        """Step 1: 路由决策."""
        return self.router.route(question)

    def retrieve(self, decision: RouteDecision) -> dict:
        """Step 2: 执行检索."""
        tool_name = decision.tool_name
        params = decision.params

        try:
            result = self.registry.execute(tool_name, **params)
        except KeyError:
            # 工具未注册 → 回退到 hybrid
            result = hybrid_search(
                query=params.get("query", params.get("keyword", "")),
                keyword=params.get("keyword", params.get("query", "")),
            )

        # 统一返回格式
        if tool_name == "vector_search":
            return {"vector_results": result, "graph_results": []}
        elif tool_name == "graph_query":
            return {"vector_results": [], "graph_results": result}
        elif tool_name == "paper_lookup":
            return {"paper_lookup_result": result, "vector_results": [], "graph_results": []}
        elif tool_name == "hybrid_search":
            return result  # 已经包含 vector_results + graph_results
        else:
            return result

    def synthesize(self, question: str, retrieval_data: dict) -> SynthesisResult:
        """Step 3: 答案合成."""
        vector_results = retrieval_data.get("vector_results", [])
        graph_results = retrieval_data.get("graph_results", [])

        # 如果有 paper_lookup_result，也加入上下文
        paper_data = retrieval_data.get("paper_lookup_result")
        if paper_data and "error" not in paper_data:
            paper_info = paper_data.get("paper", {})
            triples = paper_data.get("triples", [])
            # 把 paper 信息转为 graph_results 格式
            extra_graph = [
                {
                    "head": paper_info.get("doi", ""),
                    "head_type": "Paper",
                    "relation": "PAPER_INFO",
                    "tail": paper_info.get("title", ""),
                    "tail_type": "Paper",
                    "evidence": f"{paper_info.get('journal','')} ({paper_info.get('year','')}) — {paper_info.get('authors','')}",
                    "confidence": 1.0,
                    "paper_id": paper_info.get("doi", ""),
                }
            ] + [
                {
                    "head": t.get("head", ""),
                    "head_type": t.get("head_type", ""),
                    "relation": t.get("relation", ""),
                    "tail": t.get("tail", ""),
                    "tail_type": t.get("tail_type", ""),
                    "evidence": t.get("evidence", ""),
                    "confidence": t.get("confidence", 0),
                    "paper_id": paper_info.get("doi", ""),
                }
                for t in triples
            ]
            graph_results = list(graph_results) + extra_graph

        return self.synthesizer.generate(question, vector_results, graph_results)

    # ------------------------------------------------------------------
    # 便捷接口: 一步完成
    # ------------------------------------------------------------------

    def answer(self, question: str) -> RAGResponse:
        """端到端 RAG 检索 + 合成.

        Args:
            question: 用户问题（建议已由队友做提示词改写）

        Returns:
            RAGResponse 包含 answer, citations, route_decision
        """
        t0 = time.monotonic()

        try:
            # Step 1: 路由
            decision = self.route(question)

            # Step 2: 检索
            retrieval_data = self.retrieve(decision)

            # Step 3: 合成
            synth_result = self.synthesize(question, retrieval_data)

            elapsed = (time.monotonic() - t0) * 1000
            return RAGResponse(
                question=question,
                answer=synth_result.answer,
                citations=synth_result.citations,
                route_decision=decision,
                retrieval_data=retrieval_data,
                elapsed_ms=round(elapsed, 1),
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            return RAGResponse(
                question=question,
                answer=f"RAG 流程异常: {str(e)}",
                elapsed_ms=round(elapsed, 1),
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 批量
    # ------------------------------------------------------------------

    def answer_batch(
        self, questions: list[str], verbose: bool = True
    ) -> list[RAGResponse]:
        """批量回答多个问题."""
        results = []
        for i, q in enumerate(questions):
            if verbose:
                print(f"[{i+1}/{len(questions)}] {q[:60]}...")
            results.append(self.answer(q))
        return results
