"""工具注册表 —— 统一管理所有检索工具和 Agent 工具.

LLM function-calling 需要的 tool definitions 由这里生成。
后续队友的 6 个 Agent 也通过 register() 注册进来。

使用方式:
    registry = ToolRegistry()
    registry.register(vector_search_tool)
    registry.register(graph_query_tool)
    tools_json = registry.openai_tool_definitions()  # 喂给 LLM
    result = registry.execute("vector_search", query="PBL physics")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# ToolSpec —— 工具规格
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """一个可被 LLM function-calling 调用的工具."""

    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[..., Any]  # 实际执行的 Python 函数
    category: str = "retrieval"  # retrieval | agent | utility


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """工具注册表.

    支持:
    - 注册/移除工具
    - 生成 OpenAI function-calling 兼容的 tool definitions
    - 按名称调用工具
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ---- 注册 ----

    def register(self, tool: ToolSpec) -> None:
        """注册一个工具."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """移除一个工具."""
        self._tools.pop(name, None)

    # ---- 查询 ----

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_by_category(self, category: str) -> list[ToolSpec]:
        return [t for t in self._tools.values() if t.category == category]

    # ---- LLM 接口 ----

    def openai_tool_definitions(self) -> list[dict]:
        """生成 OpenAI / DeepSeek function-calling 兼容的 tools 列表.

        返回格式可直接传给 client.chat.completions.create(tools=...).
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    # ---- 执行 ----

    def execute(self, name: str, **kwargs: Any) -> Any:
        """按名称执行工具.

        Raises:
            KeyError: 工具未注册
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not found. Available: {self.list_names()}")
        return tool.handler(**kwargs)


# ===========================================================================
# 工厂函数: 创建默认的检索工具注册表
# ===========================================================================


def create_default_registry(
    vector_search_fn: Callable,
    graph_query_fn: Callable,
    paper_lookup_fn: Callable,
    hybrid_search_fn: Callable,
) -> ToolRegistry:
    """创建包含 4 个基础检索工具的注册表.

    Args:
        vector_search_fn: 向量检索函数 (query, top_k) -> list[dict]
        graph_query_fn: 图谱查询函数 (keyword, entity_type, relation_type) -> list[dict]
        paper_lookup_fn: 论文查找函数 (paper_id) -> dict
        hybrid_search_fn: 混合检索函数 (query, keyword) -> dict
    """
    registry = ToolRegistry()

    # --- vector_search ---
    registry.register(
        ToolSpec(
            name="vector_search",
            description=(
                "搜索论文全文中的具体事实、概念定义、实验细节、数值结果。"
                "适用于：查找某个具体知识点（如'建构主义学习理论'）的定义和研究发现；"
                "查找实验参数（如效应量、样本量）；"
                "查找原文中的具体论述。"
                "不适用于：查找论文间的关系模式（请用 graph_query）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询，使用中文或英文关键词提取核心概念",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量，默认 5，最大 10",
                    },
                },
                "required": ["query"],
            },
            handler=vector_search_fn,
            category="retrieval",
        )
    )

    # --- graph_query ---
    registry.register(
        ToolSpec(
            name="graph_query",
            description=(
                "查询论文知识图谱中的关系模式。"
                "适用于：查询某种教学法被哪些研究采用（如'project-based learning'被用在哪些领域）；"
                "查询某种技术改进了什么学习成果（如'virtual reality'提升了什么）；"
                "查询某个领域常用什么研究方法（如'physics education'用什么方法研究）；"
                "查询某个人群被哪些研究关注（如'undergraduate students'）。"
                "不适用于：查找具体定义或数值（请用 vector_search）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "检索关键词：教学法名、技术名、学科领域、学习成果等",
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "可选：筛选实体类型。可选值: ResearchMethod, PedagogicalMethod, Technology, SubjectDomain, LearningOutcome, StudentPopulation, Assessment, EducationalTheory, EffectSize, SampleInfo, Claim, ReportingGuideline",
                    },
                    "relation_type": {
                        "type": "string",
                        "description": "可选：筛选关系类型。可选值: USES_METHOD, ADOPTS_PEDAGOGY, APPLIES_THEORY, DEPLOYS_TECH, STUDIES_DOMAIN, TARGETS_OUTCOME, INVOLVES_POPULATION, EMPLOYS_ASSESSMENT, IMPROVES, INTEGRATES_WITH, COMPARES_WITH",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量，默认 10，最大 30",
                    },
                },
                "required": ["keyword"],
            },
            handler=graph_query_fn,
            category="retrieval",
        )
    )

    # --- paper_lookup ---
    registry.register(
        ToolSpec(
            name="paper_lookup",
            description=(
                "精确查找一篇论文的详细信息。"
                "适用于：用户指定了具体论文（DOI、标题或论文编号）；"
                "需要查看某篇论文的所有研究要素（方法、教学法、技术、样本等）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "论文标识符：DOI（如 10.3934/steme.2026023）或 paper_id（如 01_AIMS_10.3934_steme.2026023）",
                    },
                },
                "required": ["paper_id"],
            },
            handler=paper_lookup_fn,
            category="retrieval",
        )
    )

    # --- hybrid_search ---
    registry.register(
        ToolSpec(
            name="hybrid_search",
            description=(
                "同时查询向量库和图数据库，适用于需要兼顾'关系脉络'和'原文证据'的复杂问题。"
                "适用于：比较分析（如'比较PBL和传统教学对物理成绩的影响'）；"
                "综述类问题（如'AI在物理教育中的应用有哪些'）；"
                "评估类问题（如'VR对学习效果的整体效应如何'）。"
                "会自动并行执行向量和图谱两种检索并合并结果。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于向量检索的查询（完整问题或关键词）",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "用于图谱检索的关键词（核心概念，如教学法名、技术名）",
                    },
                },
                "required": ["query", "keyword"],
            },
            handler=hybrid_search_fn,
            category="retrieval",
        )
    )

    return registry
