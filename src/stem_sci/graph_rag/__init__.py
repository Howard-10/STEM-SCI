"""GraphRAG 双层知识库模块.

组件:
  schema.py           — 实体/关系类型定义 + Triple/BatchedExtractionResult 数据模型
  prompt_templates.py — LLM 抽取 prompt（单 chunk + 批量）
  entity_extract.py   — LLM 三元组抽取器（批量、缓存、智能重试）
  cache.py            — SQLite 抽取结果缓存（单 chunk + 批量双层缓存）
  chunker.py          — PDF 解析 + 分层切片（含 SHA256 缓存）
  graph_store.py      — Neo4j 图谱 CRUD（真实 UNWIND 批量写入，project_id 隔离）
  schema_registry.py  — 自举式类型演化 (SQLite)

当前 GraphRAG 实现状态:
  [x] PDF 解析
  [x] chunk 切片（含 page_start/page_end）
  [x] LLM 实体关系抽取（单 chunk + 批量）
  [x] 批量抽取保留 chunk 来源追溯
  [x] 三元组校验
  [x] 本地去重（合并 evidence + 来源）
  [x] SQLite 抽取缓存（单 chunk + 批量双层）
  [x] Neo4j 图谱写入（UNWIND 批量，project_id 隔离）
  [x] 基于实体的图查询 (query_entity / query_evidence)
  [ ] 本地 Embedding
  [ ] 向量数据库
  [ ] 向量检索
  [ ] 混合检索 (图谱 + 向量)
  [ ] 图谱子图扩展检索
  [ ] 基于证据的最终答案生成

本轮职责边界:
  当前 GraphRAG 模块负责:
    PDF 解析 → chunk 切片 → 实体与关系抽取 → 三元组校验
    → 本地去重 → SQLite 抽取缓存 → Neo4j 图谱写入 → 图谱查询

  当前暂不负责:
    FAISS 向量检索 / BM25 检索 / Embedding 生成 / 向量数据库
    / 向量与图谱混合召回 / 最终 RAG 答案生成

快速开始:
    from stem_sci.graph_rag import EntityExtractor, GraphStore, SchemaRegistry

    extractor = EntityExtractor.from_preset("deepseek-cloud",
        api_key="sk-xxx", api_base="https://api.deepseek.com/v1")
    store = GraphStore.from_env()
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schema import (
    BATCH_PROMPT_VERSION,
    PROFILE_PROMPT_VERSION,
    ENTITY_TYPE_DEFINITIONS,
    PROMPT_VERSION,
    RELATION_TYPE_DEFINITIONS,
    SCHEMA_VERSION,
    BatchCacheEntry,
    BatchedExtractionResult,
    BatchFailure,
    CacheEntry,
    ChunkTriples,
    EntityType,
    ExtractionResult,
    RelationType,
    Triple,
)
from .schema_registry import SchemaRegistry

# ── 缓存层 ──
from .cache import CacheStats, ExtractionCache

# ── 可选依赖：openai ──
try:
    from .entity_extract import PRESETS, EntityExtractor, ExtractionError, ExtractionStats  # noqa: F401
except ImportError:
    PRESETS = {}

    class EntityExtractor:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError("EntityExtractor requires 'openai'. Install: pip install openai")

# ── 可选依赖：neo4j ──
try:
    from .graph_store import GraphStore, Neo4jConfig  # noqa: F401
except ImportError:
    class GraphStore:  # type: ignore[no-redef]
        @classmethod
        def from_env(cls, *args, **kwargs):
            raise ImportError(
                "GraphStore requires 'neo4j'. Install it before graph writes: "
                "python -m pip install neo4j"
            )

        def __init__(self, *args, **kwargs):
            raise ImportError("GraphStore requires 'neo4j'. Install: pip install neo4j")


# ── 未来接口：Retriever (预留，本轮不实现) ──

@runtime_checkable
class Retriever(Protocol):
    """检索器协议 —— 为未来向量检索 + 混合检索预留.

    本轮不实现完整检索系统，仅定义接口。
    """

    def retrieve(self, query: str, project_id: str, top_k: int) -> list[dict]:
        """检索相关三元组/证据."""
        ...


__all__ = [
    # 抽取器
    "EntityExtractor",
    "ExtractionError",
    "ExtractionStats",
    "PRESETS",
    # 图谱存储
    "GraphStore",
    "Neo4jConfig",
    # Schema
    "SchemaRegistry",
    "EntityType",
    "RelationType",
    "Triple",
    "ExtractionResult",
    "BatchedExtractionResult",
    "ChunkTriples",
    "BatchFailure",
    "CacheEntry",
    "BatchCacheEntry",
    "ENTITY_TYPE_DEFINITIONS",
    "RELATION_TYPE_DEFINITIONS",
    "SCHEMA_VERSION",
    "PROMPT_VERSION",
    "BATCH_PROMPT_VERSION",
    "PROFILE_PROMPT_VERSION",
    # 缓存
    "ExtractionCache",
    "CacheStats",
    # 未来接口
    "Retriever",
]
