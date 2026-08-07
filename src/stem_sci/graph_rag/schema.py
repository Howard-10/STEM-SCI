"""STEM 教育文献知识图谱 Schema 定义.

三层渐进式 Schema —— L2 研究要素层 + L3 研究发现层（合并实现）:

L2 研究要素:
  Entity:  ResearchMethod | EducationalTheory | Technology | PedagogicalMethod
          SubjectDomain | LearningOutcome | StudentPopulation | Assessment
  Relation: USES_METHOD | APPLIES_THEORY | DEPLOYS_TECH | ADOPTS_PEDAGOGY
            STUDIES_DOMAIN | TARGETS_OUTCOME | INVOLVES_POPULATION
            EMPLOYS_ASSESSMENT | INTEGRATES_WITH | IMPROVES

L3 研究发现:
  Entity:  Claim | Evidence | EffectSize | SampleInfo | ComparisonCondition
  Relation: CLAIMS | SUPPORTED_BY | HAS_EFFECT_SIZE | HAS_SAMPLE | COMPARES_WITH

自举机制:
  闭合核心 + 开放边界 —— 核心类型覆盖 80% 抽取，遇到无法归类的实体/关系时
  使用 Concept / RELATED_TO 兜底，同时 LLM 给出 new_type_suggestion。
  积累到阈值后人工确认 → 升级为正式类型。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# 核心 Schema — 实体与关系类型
# ============================================================================


class EntityType(str, Enum):
    """L2 + L3 合并实体类型."""

    # ── L2 研究要素 ──
    RESEARCH_METHOD = "ResearchMethod"
    EDUCATIONAL_THEORY = "EducationalTheory"
    TECHNOLOGY = "Technology"
    PEDAGOGICAL_METHOD = "PedagogicalMethod"
    SUBJECT_DOMAIN = "SubjectDomain"
    LEARNING_OUTCOME = "LearningOutcome"
    STUDENT_POPULATION = "StudentPopulation"
    ASSESSMENT = "Assessment"

    # ── L3 研究发现 ──
    CLAIM = "Claim"
    EVIDENCE = "Evidence"
    EFFECT_SIZE = "EffectSize"
    SAMPLE_INFO = "SampleInfo"
    COMPARISON_CONDITION = "ComparisonCondition"

    # ── 自举兜底 ──
    CONCEPT = "Concept"

    # 论文节点：论文级关系的唯一合法 head 类型。
    PAPER = "Paper"

    # 报告规范：PRISMA、STROBE、CONSORT 等研究设计与报告标准。
    REPORTING_GUIDELINE = "ReportingGuideline"


class RelationType(str, Enum):
    """L2 + L3 合并关系类型."""

    # ── L2 论文→要素 ──
    USES_METHOD = "USES_METHOD"           # 研究方法 / 报告规范
    ADOPTS_PEDAGOGY = "ADOPTS_PEDAGOGY"   # 教学法（与 USES_METHOD 区分）
    APPLIES_THEORY = "APPLIES_THEORY"
    DEPLOYS_TECH = "DEPLOYS_TECH"
    STUDIES_DOMAIN = "STUDIES_DOMAIN"
    TARGETS_OUTCOME = "TARGETS_OUTCOME"
    INVOLVES_POPULATION = "INVOLVES_POPULATION"
    EMPLOYS_ASSESSMENT = "EMPLOYS_ASSESSMENT"
    HAS_SAMPLE = "HAS_SAMPLE"

    # ── L2 跨实体 ──
    INTEGRATES_WITH = "INTEGRATES_WITH"
    IMPROVES = "IMPROVES"

    # ── L3 研究发现 ──
    CLAIMS = "CLAIMS"
    SUPPORTED_BY = "SUPPORTED_BY"
    HAS_EFFECT_SIZE = "HAS_EFFECT_SIZE"
    COMPARES_WITH = "COMPARES_WITH"

    # ── 自举兜底 ──
    RELATED_TO = "RELATED_TO"


# ============================================================================
# 实体类型元数据（供 prompt 使用）
# ============================================================================

ENTITY_TYPE_DEFINITIONS: dict[EntityType, str] = {
    # L2
    EntityType.RESEARCH_METHOD: "研究方法: systematic review / meta-analysis / quasi-experiment / mixed methods / RCT / bibliometric analysis / case study / design-based research",
    EntityType.EDUCATIONAL_THEORY: "教育理论/框架: constructivism / TPACK / self-regulated learning / social cognitive theory / van Hiele model / cognitive load theory / PRISMA",
    EntityType.TECHNOLOGY: "技术/工具: ChatGPT/GenAI / VR/AR / 3D printing / digital simulations / learning analytics / IoT / intelligent tutoring system / Tinkercad",
    EntityType.PEDAGOGICAL_METHOD: "教学方法: project-based learning / inquiry-based learning / collaborative learning / flipped classroom / design thinking / scaffolding / game-based learning / problem-based learning",
    EntityType.SUBJECT_DOMAIN: "学科领域: mechanics / thermodynamics / electromagnetism / modern physics / optics / waves / redox reactions / density / kinematics / electronics",
    EntityType.LEARNING_OUTCOME: "学习成果: critical thinking / conceptual understanding / creativity / engagement / problem-solving / self-efficacy / academic achievement / scientific literacy / technical thinking",
    EntityType.STUDENT_POPULATION: "学生群体: pre-service teachers / high school students / undergraduate students / primary students / graduate students / in-service teachers",
    EntityType.ASSESSMENT: "评估工具: pre-post test / survey questionnaire / interview / eye-tracking / classroom observation / rubric / think-aloud protocol / standardized test",

    # L3
    EntityType.CLAIM: "研究发现/断言: 论文中明确提出的研究结论，如 'PBL significantly improved critical thinking' / 'AI integration showed moderate effect on engagement'",
    EntityType.EVIDENCE: "证据类型: statistical test (t-test, ANOVA) / qualitative coding / meta-analytic estimate / descriptive statistics / regression coefficient / thematic analysis",
    EntityType.EFFECT_SIZE: "效应量: Cohen's d / Hedges' g / eta-squared / R² / odds ratio / standardized mean difference / 具体数值如 d=0.78",
    EntityType.SAMPLE_INFO: "样本信息: 样本量 (N=172) / 人口统计特征 / 实验分组 (experimental vs control) / 地域 (Indonesia, Turkey, ...)",
    EntityType.COMPARISON_CONDITION: "对照条件: control group / traditional instruction / pre-intervention baseline / alternative treatment / business-as-usual",

    # 兜底
    EntityType.CONCEPT: "【兜底】无法归入以上类型的其他概念，必须在 new_type_suggestion 字段建议新类型名称",
    EntityType.PAPER: "论文节点：论文级关系的唯一合法 head 类型",
    EntityType.REPORTING_GUIDELINE: "报告规范/研究设计标准: PRISMA / STROBE / CONSORT / MOOSE / STARLITE 等",
}

RELATION_TYPE_DEFINITIONS: dict[RelationType, str] = {
    # L2
    RelationType.USES_METHOD: "(论文) → 使用研究方法/报告规范 → (方法/规范)",
    RelationType.ADOPTS_PEDAGOGY: "(论文) → 采用教学法 → (教学法)",
    RelationType.APPLIES_THEORY: "(论文) → 应用/基于理论 → (理论)",
    RelationType.DEPLOYS_TECH: "(论文) → 部署/使用技术 → (技术)",
    RelationType.STUDIES_DOMAIN: "(论文) → 研究学科领域 → (领域)",
    RelationType.TARGETS_OUTCOME: "(论文) → 关注/测量学习成果 → (成果)",
    RelationType.INVOLVES_POPULATION: "(论文) → 涉及学生群体 → (群体)",
    RelationType.EMPLOYS_ASSESSMENT: "(论文) → 使用评估工具 → (评估)",
    RelationType.HAS_SAMPLE: "(论文) → 样本信息 → (SampleInfo)",
    RelationType.HAS_EFFECT_SIZE: "(论文/Claim) → 效应量 → (EffectSize)",
    RelationType.INTEGRATES_WITH: "(技术/教学法) → 整合/结合 → (技术/教学法)",
    RelationType.IMPROVES: "(教学法/技术) → 提升/改善 → (学习成果)",

    # L3
    RelationType.CLAIMS: "(论文) → 提出发现/断言 → (Claim)",
    RelationType.SUPPORTED_BY: "(Claim) → 被证据支持 → (Evidence)",
    RelationType.COMPARES_WITH: "(干预/教学法) → 对比/比较 → (对照条件)",

    # 兜底
    RelationType.RELATED_TO: "【兜底】两个实体存在关联但无法归入以上关系，必须在 new_type_suggestion 字段建议新关系名称",
}

# 关系主语（head）类型约束
RELATION_HEAD_CONSTRAINTS: dict[RelationType, list[EntityType]] = {
    RelationType.USES_METHOD: [EntityType.PAPER],
    RelationType.ADOPTS_PEDAGOGY: [EntityType.PAPER],
    RelationType.APPLIES_THEORY: [EntityType.PAPER],
    RelationType.DEPLOYS_TECH: [EntityType.PAPER],
    RelationType.STUDIES_DOMAIN: [EntityType.PAPER],
    RelationType.TARGETS_OUTCOME: [EntityType.PAPER],
    RelationType.INVOLVES_POPULATION: [EntityType.PAPER],
    RelationType.EMPLOYS_ASSESSMENT: [EntityType.PAPER],
    RelationType.HAS_SAMPLE: [EntityType.PAPER],
    RelationType.CLAIMS: [EntityType.PAPER],
    RelationType.HAS_EFFECT_SIZE: [EntityType.PAPER, EntityType.CLAIM, EntityType.PEDAGOGICAL_METHOD, EntityType.TECHNOLOGY, EntityType.CONCEPT],
    RelationType.INTEGRATES_WITH: [
        EntityType.TECHNOLOGY,
        EntityType.PEDAGOGICAL_METHOD,
        EntityType.RESEARCH_METHOD,
        EntityType.CONCEPT,
    ],
    RelationType.IMPROVES: [
        EntityType.PEDAGOGICAL_METHOD,
        EntityType.TECHNOLOGY,
        EntityType.RESEARCH_METHOD,
        EntityType.CONCEPT,
    ],
    # L3
    RelationType.SUPPORTED_BY: [
        EntityType.CLAIM,
        EntityType.CONCEPT,
    ],
    RelationType.COMPARES_WITH: [
        EntityType.PEDAGOGICAL_METHOD,
        EntityType.TECHNOLOGY,
        EntityType.INTERVENTION if "INTERVENTION" in EntityType.__members__ else EntityType.CONCEPT,
    ],
    RelationType.RELATED_TO: [t for t in EntityType],
}


# ============================================================================
# Schema & Prompt 版本 —— 修改后缓存自动失效
# ============================================================================

SCHEMA_VERSION = "2.2.0"
PROMPT_VERSION = "2.2.0"
BATCH_PROMPT_VERSION = "2.2.0"
PROFILE_PROMPT_VERSION = "3.1.0"


# ============================================================================
# 数据模型
# ============================================================================


class Triple(BaseModel):
    """单个知识三元组，含溯源证据与 chunk 来源."""

    head: str = Field(
        description="主语实体名称（规范化标准名，如 'project-based learning' 非 'PBL'）",
        min_length=1,
    )
    head_type: str = Field(
        description="主语实体类型，必须是 EntityType 枚举值之一",
    )
    relation: str = Field(
        description="关系类型，必须是 RelationType 枚举值之一",
    )
    tail: str = Field(
        description="宾语实体名称",
        min_length=1,
    )
    tail_type: str = Field(
        description="宾语实体类型，必须是 EntityType 枚举值之一",
    )
    evidence: str = Field(
        description="支持此三元组的原始文本摘录（原文，溯源核验）",
        min_length=1,
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="抽取置信度 (0.0–1.0)",
    )
    new_type_suggestion: Optional[str] = Field(
        default=None,
        description="当 head_type/tail_type=Concept 或 relation=RELATED_TO 时，"
        "建议的新类型名称（kebab-case，如 'citizen-science'）",
    )
    layer: str = Field(
        default="L2",
        description="所属层级: L2 (研究要素) 或 L3 (研究发现)",
    )
    # ── chunk 来源追溯 ──
    source_chunk_id: str = Field(
        default="",
        description="来源 chunk 标识，如 'paper_doi_chunk_0001'",
    )
    source_chunk_index: int = Field(
        default=-1,
        description="来源 chunk 在文档中的序号",
    )
    # ── 去重后多来源追踪 ──
    source_chunk_ids: list[str] = Field(
        default_factory=list,
        description="去重合并后所有来源 chunk_id 列表",
    )
    source_chunk_indices: list[int] = Field(
        default_factory=list,
        description="去重合并后所有来源 chunk_index 列表",
    )


class ExtractionResult(BaseModel):
    """单次抽取的完整结果."""

    paper_id: str = Field(description="来源论文 ID（DOI 或自定义标识）")
    chunk_index: int = Field(default=0, description="文本块索引")
    triples: list[Triple] = Field(default_factory=list, description="抽取的三元组列表")
    raw_response: Optional[str] = Field(
        default=None, description="LLM 原始响应（调试用）"
    )
    retry_count: int = Field(default=0, description="重试次数")
    cache_hit: bool = Field(default=False, description="是否命中缓存")
    merge_mode: str = Field(default="local", description="去重模式: local | llm")


class ChunkTriples(BaseModel):
    """单个 chunk 的抽取结果，用于批量抽取."""

    chunk_id: str = Field(description="chunk 标识, 如 'chunk_0001'")
    chunk_index: int = Field(default=0, description="chunk 序号")
    triples: list[Triple] = Field(default_factory=list, description="该 chunk 的三元组列表")
    status: str = Field(default="success", description="抽取状态: success | failed")
    error_message: str = Field(default="", description="失败原因")


class BatchFailure(BaseModel):
    """单个 batch 的失败信息."""

    batch_index: int = Field(description="batch 在本次抽取中的序号")
    chunk_indices: list[int] = Field(default_factory=list, description="该 batch 包含的 chunk 序号")
    status: str = Field(default="failed", description="状态: failed")
    error_type: str = Field(default="unknown", description="错误类型: json_parse_error | timeout | api_error | provenance_error")
    error_message: str = Field(default="", description="错误详情")
    retry_count: int = Field(default=0, description="已重试次数")
    raw_response_snippet: str = Field(default="", description="原始响应摘要（前 500 字符）")


class BatchedExtractionResult(BaseModel):
    """批量抽取的完整结果."""

    paper_id: str = Field(description="来源论文 ID")
    chunks: list[ChunkTriples] = Field(default_factory=list, description="各 chunk 结果")
    total_triples: int = Field(default=0, description="三元组总数（去重后）")
    raw_responses: list[str] = Field(default_factory=list, description="各 batch 的原始响应")
    batch_count: int = Field(default=0, description="API 请求次数")
    cache_hits: int = Field(default=0, description="缓存命中 chunk 数")
    cache_misses: int = Field(default=0, description="缓存未命中 chunk 数")
    failures: list[BatchFailure] = Field(default_factory=list, description="失败的 batch 列表")
    merge_mode: str = Field(default="local", description="去重模式: local | llm")
    retry_count: int = Field(default=0, description="总重试次数")
    elapsed_seconds: float = Field(default=0.0, description="总耗时")
    mode: str = Field(default="FULL_AUDIT", description="抽取模式: PROFILE | EVIDENCE | FULL_AUDIT")
    max_triples: int = Field(default=0, description="模式允许的最大三元组数，0 表示不限制")
    discarded_triples: int = Field(default=0, description="质量筛选或数量上限丢弃的三元组数")


class BatchCacheEntry(BaseModel):
    """批量缓存条目."""

    batch_cache_key: str = Field(description="批量缓存键")
    paper_id: str = ""
    chunk_sha256s: list[str] = Field(default_factory=list, description="有序 chunk SHA256 列表")
    model_id: str = ""
    batch_size: int = 0
    batch_prompt_version: str = ""
    schema_version: str = ""
    raw_response: str = ""
    chunk_results: list[ChunkTriples] = Field(default_factory=list, description="每个 chunk 的解析结果")
    created_at: str = ""
    retry_count: int = 0


class CacheEntry(BaseModel):
    """缓存条目."""

    cache_key: str = Field(description="缓存键")
    paper_id: str = ""
    chunk_index: int = 0
    chunk_sha256: str = ""
    model_id: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    raw_response: str = ""
    triples: list[Triple] = Field(default_factory=list)
    created_at: str = ""
    retry_count: int = 0


class EntityInfo(BaseModel):
    """图谱中已存储的实体摘要."""

    name: str
    entity_type: str
    project_id: str
    occurrence_count: int = 1
    first_seen_paper: str = ""


class EntityNormalization(BaseModel):
    """实体归一化映射."""

    canonical: str = Field(description="规范名称")
    aliases: list[str] = Field(default_factory=list, description="已知别名列表")
    entity_type: str
