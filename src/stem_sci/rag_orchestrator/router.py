"""路由模块 —— LLM 自动判断查询策略.

结合规则匹配和 LLM function-calling:
    - 规则命中 → 直接路由（零 LLM 消耗）
    - 规则未命中 → LLM function-calling 选择工具

使用方式:
    router = Router(config, registry)
    decision = router.route("项目式学习对物理概念理解有什么效果？")
    # decision.tool_name → "hybrid_search"
    # decision.params    → {"query": "...", "keyword": "..."}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .config import LLMConfig
from .tool_registry import ToolRegistry

# ===========================================================================
# 路由决策结果
# ===========================================================================


@dataclass
class RouteDecision:
    """LLM 路由决策."""

    tool_name: str
    params: dict = field(default_factory=dict)
    reasoning: str = ""
    method: str = ""  # "rule" | "llm" | "fallback"
    llm_raw_response: str = ""

    @classmethod
    def fallback(cls, question: str) -> "RouteDecision":
        """当一切方法都失败时的兜底策略."""
        return cls(
            tool_name="hybrid_search",
            params={"query": question, "keyword": question},
            reasoning="路由失败，回退到混合检索",
            method="fallback",
        )


# ===========================================================================
# 规则匹配 —— 快速路由，省 LLM 调用
# ===========================================================================

# (正则, 目标工具) —— 按顺序匹配，命中即停
ROUTE_RULES: list[tuple[str, str]] = [
    # 精确查找某篇论文
    (r"(doi|DOI)[：:\s]*10\.\d{4,}|第.*篇.*论文|查找.*论文|查.*论文|论文.*编号",
     "paper_lookup"),
    (r"\b10\.\d{4,}/", "paper_lookup"),

    # 关系型 → 图数据库
    (r"(什么|哪些|哪种).{0,6}(方法|教学法|技术|理论|工具).{0,6}(用于|用在|适用|改善|提高|提升|改进)",
     "graph_query"),
    (r"(关系|关联|模式|连接|网络|图谱|影响路径)",
     "graph_query"),
    (r"(采用|使用|运用).{0,4}(什么|哪种|哪些).{0,4}(方法|教学法|技术)",
     "graph_query"),
    (r"(什么|哪些).{0,4}(方法|技术|教学法).{0,4}(最|更).{0,4}(有效|常用)",
     "graph_query"),

    # 事实/定义/数值 → 向量库
    (r"(定义|是什么|概念|含义|解释).{0,10}(什么|哪|如何)",
     "vector_search"),
    (r"(效应量|d=|g=|p值|样本量|具体|原文|原文中|文中提到)",
     "vector_search"),
    (r"(细节|详细|具体怎么|如何实施|怎么做|步骤)",
     "vector_search"),

    # 比较/综述/评估 → 混合检索
    (r"(比较|对比|区别|差异).{0,4}(和|与|跟)",
     "hybrid_search"),
    (r"(综述|总结|概述|全貌|整体|综合|评估).{0,8}(情况|效果|应用|研究)",
     "hybrid_search"),
    (r"(有哪些|汇总|梳理|归纳|整理).{0,8}(研究|论文|方法|技术|应用|成果|发现)",
     "hybrid_search"),
]


def rule_based_route(question: str) -> Optional[RouteDecision]:
    """规则匹配路由.

    Returns:
        RouteDecision 如果命中，否则 None.
    """
    for pattern, tool_name in ROUTE_RULES:
        if re.search(pattern, question, re.IGNORECASE):
            if tool_name == "paper_lookup":
                # 尝试提取 DOI
                doi_match = re.search(r"10\.\d{4,}/[^\s\)]+", question)
                params = {"paper_id": doi_match.group(0) if doi_match else question}
                return RouteDecision(
                    tool_name=tool_name,
                    params=params,
                    reasoning=f"规则匹配: {pattern}",
                    method="rule",
                )
            elif tool_name == "vector_search":
                return RouteDecision(
                    tool_name=tool_name,
                    params={"query": question, "top_k": 5},
                    reasoning=f"规则匹配: {pattern}",
                    method="rule",
                )
            elif tool_name == "graph_query":
                return RouteDecision(
                    tool_name=tool_name,
                    params={"keyword": question, "limit": 15},
                    reasoning=f"规则匹配: {pattern}",
                    method="rule",
                )
            else:  # hybrid_search
                return RouteDecision(
                    tool_name=tool_name,
                    params={"query": question, "keyword": question},
                    reasoning=f"规则匹配: {pattern}",
                    method="rule",
                )
    return None


# ===========================================================================
# LLM Router —— function-calling 路由
# ===========================================================================

ROUTER_SYSTEM_PROMPT = """你是 STEM 教育研究知识图谱的检索路由器。

你的任务：根据用户问题，选择最合适的检索工具。

## 可用工具说明

| 工具 | 适用场景 | 不适用 |
|------|---------|--------|
| vector_search | 查具体事实、定义、数值、原文细节 | 查关系模式 |
| graph_query | 查方法-领域-成果之间的关系网络 | 查具体定义 |
| hybrid_search | 复杂问题，需要关系脉络+原文证据 | 简单事实查询 |
| paper_lookup | 用户指定了某篇具体论文 | 泛泛而问 |

## 决策原则

1. 关系型问题 → graph_query（什么方法用在什么领域？什么技术改进了什么？）
2. 事实型问题 → vector_search（某概念的定义？某实验的效应量？）
3. 比较/综述/评估 → hybrid_search（A和B比较？有哪些应用？整体效果如何？）
4. 指定论文 → paper_lookup（DOI 或论文编号明确时）

## 输出格式

严格输出 JSON，不要加 markdown 代码块标记：
{"tool": "工具名", "query": "检索查询", "keyword": "图谱关键词", "reasoning": "简短理由"}
"""


class Router:
    """LLM 路由器：规则 + function-calling 双通道."""

    def __init__(self, config: LLMConfig, registry: ToolRegistry) -> None:
        self.config = config
        self.registry = registry
        self._client = config.create_client()

    def route(self, question: str) -> RouteDecision:
        """判断查询应该走哪个工具.

        优先级: 规则匹配 > LLM function-calling > 兜底 hybrid_search
        """
        # Step 1: 规则匹配
        decision = rule_based_route(question)
        if decision is not None:
            return decision

        # Step 2: LLM function-calling
        try:
            return self._llm_route(question)
        except Exception as e:
            # Step 3: 兜底
            d = RouteDecision.fallback(question)
            d.reasoning = f"LLM路由异常({e})，回退到混合检索"
            return d

    def _llm_route(self, question: str) -> RouteDecision:
        """使用 LLM function-calling 做路由."""
        tools = self.registry.openai_tool_definitions()

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            tools=tools,
            tool_choice="auto",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        msg = response.choices[0].message

        # 如果 LLM 选择了 tool_call
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_name = tc.function.name
            try:
                params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                params = {}
            return RouteDecision(
                tool_name=tool_name,
                params=params,
                reasoning=f"LLM function-calling → {tool_name}",
                method="llm",
                llm_raw_response=tc.function.arguments,
            )

        # LLM 没有选择 tool_call，尝试从文本中解析
        content = msg.content or ""
        return self._parse_text_decision(content, question)

    def _parse_text_decision(self, content: str, question: str) -> RouteDecision:
        """从 LLM 文本回复中解析路由决策."""
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group(0))
                tool = data.get("tool", "hybrid_search")
                query = data.get("query", question)
                keyword = data.get("keyword", question)
                return RouteDecision(
                    tool_name=tool,
                    params={"query": query, "keyword": keyword},
                    reasoning=data.get("reasoning", "LLM 文本解析"),
                    method="llm",
                    llm_raw_response=content,
                )
        except json.JSONDecodeError:
            pass

        # 实在解析不了 → 回退
        return RouteDecision.fallback(question)
