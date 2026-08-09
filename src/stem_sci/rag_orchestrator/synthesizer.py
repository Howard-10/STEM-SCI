"""答案合成模块 —— 将检索结果喂给 LLM 生成带溯源的最终答案.

使用方式:
    synth = Synthesizer(config)
    result = synth.generate(
        question="项目式学习对物理概念理解有什么效果？",
        vector_results=[...],
        graph_results=[...],
    )
    # result.answer    → markdown 格式答案
    # result.citations → 引用来源列表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import LLMConfig

# ===========================================================================
# 数据结构
# ===========================================================================


@dataclass
class Citation:
    """单条引用来源."""

    paper_title: str
    doi: str = ""
    evidence: str = ""
    year: str = ""
    source_type: str = ""  # "vector" | "graph"


@dataclass
class SynthesisResult:
    """答案合成结果."""

    answer: str
    citations: list[Citation] = field(default_factory=list)
    citation_count: int = 0
    source_breakdown: dict = field(default_factory=dict)  # {"vector": N, "graph": M}

    def __post_init__(self):
        self.citation_count = len(self.citations)
        self.source_breakdown = {}
        for c in self.citations:
            s = c.source_type or "unknown"
            self.source_breakdown[s] = self.source_breakdown.get(s, 0) + 1


# ===========================================================================
# System Prompt
# ===========================================================================

SYNTHESIZER_SYSTEM_PROMPT = """你是 STEM 教育研究助手，负责基于检索到的论文证据回答用户问题。

## 回答要求

1. **基于证据**：每个主张都必须引用来源，格式为 `[来源N]`
2. **标注可信度**：如果证据不足或矛盾，请明确说明
3. **不编造**：如果检索结果不足以回答问题，直接说"当前检索结果不足以回答这个问题"
4. **结构化**：使用 markdown 组织答案，包含：
   - 直接回答（1-2句总结）
   - 详细分析（分点论述，每点引用来源）
   - 证据概要表（可选，复杂问题时使用）

## 输出格式

```
## 回答
[直接回答]

## 详细分析
- **要点1**：... [来源1][来源2]
- **要点2**：... [来源3]

## 来源
[来源1] Paper Title (Year). DOI: ... — "...evidence..."
[来源2] Paper Title (Year). DOI: ... — "...evidence..."
```

## 数据源说明

- 向量检索结果：论文全文中的具体段落（text 字段）
- 图谱检索结果：论文间的关系三元组（head → relation → tail，附 evidence）
- 两种结果可能指向同一篇论文，请合并整理
"""


# ===========================================================================
# Synthesizer
# ===========================================================================


class Synthesizer:
    """LLM 答案合成器."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client = config.create_client()

    def generate(
        self,
        question: str,
        vector_results: Optional[list[dict]] = None,
        graph_results: Optional[list[dict]] = None,
    ) -> SynthesisResult:
        """生成带溯源的答案.

        Args:
            question: 用户问题
            vector_results: 向量检索结果列表
            graph_results: 图谱检索结果列表

        Returns:
            SynthesisResult 包含 answer 和 citations
        """
        # 构建上下文
        context = self._build_context(vector_results or [], graph_results or [])

        # 调用 LLM 生成
        user_prompt = f"""## 用户问题
{question}

## 检索到的证据
{context}

请基于以上证据回答问题。"""

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"答案合成失败: {str(e)}"

        # 提取引用
        citations = self._extract_citations(vector_results or [], graph_results or [])

        return SynthesisResult(answer=answer, citations=citations)

    def _build_context(
        self, vector_results: list[dict], graph_results: list[dict]
    ) -> str:
        """构建喂给 LLM 的上下文."""
        parts = []

        # 向量检索结果
        if vector_results:
            valid = [r for r in vector_results if "error" not in r]
            if valid:
                parts.append("### 向量检索（论文全文段落）\n")
                for i, r in enumerate(valid, 1):
                    parts.append(
                        f"**[来源V{i}]** {r.get('paper_title', 'Unknown')} "
                        f"({r.get('year', '?')}) — DOI: {r.get('doi', 'N/A')}\n"
                        f"> {r.get('text', '')}\n"
                    )

        # 图谱检索结果
        if graph_results:
            valid = [r for r in graph_results if "error" not in r]
            if valid:
                parts.append("### 图谱检索（关系三元组）\n")
                for i, r in enumerate(valid, 1):
                    if r.get("relation") == "PAPER_MATCH":
                        parts.append(
                            f"**[来源G{i}]** 论文匹配: {r.get('tail', '')}\n"
                            f"> {r.get('evidence', '')}\n"
                        )
                    else:
                        parts.append(
                            f"**[来源G{i}]** {r.get('head', '')} "
                            f"--[{r.get('relation', '')}]--> {r.get('tail', '')}"
                            f" ({r.get('tail_type', '')})\n"
                            f"> evidence: {r.get('evidence', '')}\n"
                            f"> confidence: {r.get('confidence', 0):.2f}\n"
                        )

        if not parts:
            parts.append("（未检索到相关证据）")

        return "\n".join(parts)

    def _extract_citations(
        self, vector_results: list[dict], graph_results: list[dict]
    ) -> list[Citation]:
        """从检索结果中提取引用列表."""
        citations = []
        seen_titles = set()

        for r in vector_results:
            if "error" in r:
                continue
            title = r.get("paper_title", "")
            if title and title not in seen_titles:
                seen_titles.add(title)
                citations.append(
                    Citation(
                        paper_title=title,
                        doi=r.get("doi", ""),
                        evidence=(r.get("text") or "")[:200],
                        year=str(r.get("year", "")),
                        source_type="vector",
                    )
                )

        for r in graph_results:
            if "error" in r or r.get("relation") == "PAPER_MATCH":
                continue
            # 图谱结果按 paper_id 归并
            pid = r.get("paper_id", "")
            if pid and pid not in seen_titles:
                seen_titles.add(pid)
                citations.append(
                    Citation(
                        paper_title=pid,
                        evidence=(r.get("evidence") or "")[:200],
                        source_type="graph",
                    )
                )

        return citations
