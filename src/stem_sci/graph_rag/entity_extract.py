"""LLM 驱动的科研三元组抽取.

支持任意 OpenAI 兼容 API，预设多种模型，包含批量抽取、缓存、智能重试。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from openai import (
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    OpenAI,
)

from .cache import ExtractionCache
from .prompt_templates import (
    MERGE_SYSTEM_PROMPT,
    PROFILE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_batch_user_prompt,
    build_merge_prompt,
    build_profile_user_prompt,
    build_user_prompt,
)
from .schema import (
    BATCH_PROMPT_VERSION,
    PROFILE_PROMPT_VERSION,
    SCHEMA_VERSION,
    BatchFailure,
    BatchedExtractionResult,
    ChunkTriples,
    EntityType,
    ExtractionResult,
    RelationType,
    RELATION_HEAD_CONSTRAINTS,
    Triple,
)


# ============================================================================
# 环境变量 → 凭据读取
# ============================================================================


def _env(key: str, default: str = "") -> str:
    val = os.getenv(f"STEM_KB_{key}", "")
    if val:
        return val
    fallbacks = {
        "LLM_API_KEY": ["OPENAI_API_KEY", "LLM_API_KEY"],
        "LLM_API_BASE": ["OPENAI_API_BASE", "LLM_API_BASE"],
        "LLM_MODEL": ["LLM_MODEL"],
    }
    for fb in fallbacks.get(key, []):
        fb_val = os.getenv(fb, "")
        if fb_val:
            return fb_val
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


# ── 可配置参数 ──
CHUNKS_PER_REQUEST = _env_int("CHUNKS_PER_REQUEST", 3)
MAX_WORKERS = _env_int("MAX_WORKERS", 1)
MAX_RETRIES = _env_int("MAX_RETRIES", 1)
RETRY_DELAY = _env_float("RETRY_DELAY", 1.0)
MAX_TOKENS = _env_int("MAX_TOKENS", 2048)
TIMEOUT = _env_float("TIMEOUT", 60.0)
MERGE_MODE = _env("MERGE_MODE", "local")
CACHE_DIR = _env("CACHE_DIR", "")

# 论文级关系必须从 Paper 节点指向实际研究对象，不能用自循环占位。
# USES_METHOD 用于研究方法/报告规范，ADOPTS_PEDAGOGY 用于教学法。
PAPER_RELATIONS = frozenset({
    RelationType.USES_METHOD.value,
    RelationType.ADOPTS_PEDAGOGY.value,
    RelationType.APPLIES_THEORY.value,
    RelationType.DEPLOYS_TECH.value,
    RelationType.STUDIES_DOMAIN.value,
    RelationType.TARGETS_OUTCOME.value,
    RelationType.INVOLVES_POPULATION.value,
    RelationType.EMPLOYS_ASSESSMENT.value,
    RelationType.CLAIMS.value,
    RelationType.HAS_SAMPLE.value,
    RelationType.HAS_EFFECT_SIZE.value,
})
MAX_ENTITY_CHARS = 160
MAX_ENTITY_WORDS = 24
PROFILE_MAX_TRIPLES = _env_int("PROFILE_MAX_TRIPLES", 30)
PROFILE_MIN_TRIPLES = _env_int("PROFILE_MIN_TRIPLES", 8)
PROFILE_MAX_RELATED_TO = _env_int("PROFILE_MAX_RELATED_TO", 2)
PROFILE_MAX_CLAIMS = _env_int("PROFILE_MAX_CLAIMS", 5)


# ============================================================================
# 模型定价 (¥/百万 tokens) —— 用于成本估算
# ============================================================================

PRICING_PER_MILLION: dict[str, dict[str, float]] = {
    "qwen-cloud":      {"input": 0.0, "output": 0.0},
    "deepseek-cloud":  {"input": 1.0, "output": 2.0},
    "glm-cloud":       {"input": 0.1, "output": 0.1},
    "deepseek":  {"input": 0.0, "output": 0.0},
    "kimi":      {"input": 0.0, "output": 0.0},
    "qwen":      {"input": 0.0, "output": 0.0},
    "glm":       {"input": 0.0, "output": 0.0},
}


def estimate_cost_yuan(preset_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING_PER_MILLION.get(preset_name, {"input": 0.0, "output": 0.0})
    return (input_tokens / 1_000_000) * pricing["input"] + \
           (output_tokens / 1_000_000) * pricing["output"]


# ============================================================================
# 预设模型配置
# ============================================================================


@dataclass
class ModelPreset:
    name: str
    model_id: str
    description: str = ""
    supports_json_mode: bool = True
    max_tokens: int = 2048
    temperature: float = 0.1


PRESETS: dict[str, ModelPreset] = {
    "deepseek": ModelPreset(
        name="DeepSeek 4.0 (校内)", model_id="ds",
        description="校内 DeepSeek — JSON 结构化输出最稳定",
    ),
    "kimi": ModelPreset(
        name="Kimi-K2.6 (校内)", model_id="moonshotai/Kimi-K2.6",
        description="校内 Kimi — 英文 STEM 文献理解力强",
    ),
    "qwen": ModelPreset(
        name="Qwen3.5-397B (校内)", model_id="Qwen3.5-397B-A17B",
        description="校内 Qwen — 综合能力强",
    ),
    "glm": ModelPreset(
        name="智谱 GLM 5.1 (校内)", model_id="/models/GLM-5.1-INT8/",
        description="校内 GLM — INT8 量化",
        supports_json_mode=False,
    ),
    "qwen-cloud": ModelPreset(
        name="通义千问 (阿里百炼云)", model_id="qwen-plus",
        description="免费 7000万 tokens",
        max_tokens=8192,
    ),
    "deepseek-cloud": ModelPreset(
        name="DeepSeek V3 (云端)", model_id="deepseek-chat",
        description="¥1-2/M, JSON 稳定",
        max_tokens=8192,
    ),
    "glm-cloud": ModelPreset(
        name="智谱 GLM-4-Flash (云端)", model_id="glm-4-flash",
        description="¥0.1/M, 极便宜",
        max_tokens=8192,
    ),
}


# ============================================================================
# 错误分类
# ============================================================================


class ExtractionError(Exception):
    """抽取失败，含分类信息."""
    def __init__(self, message: str, error_type: str = "unknown", status_code: int = 0):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code


def _is_retryable(error: Exception) -> bool:
    """判断错误是否可重试.

    可重试: timeout, connection error, 429, 500-599, JSON 解析错误
    """
    if isinstance(error, (APITimeoutError, RateLimitError)):
        return True
    if isinstance(error, InternalServerError):
        return True
    if isinstance(error, APIError):
        try:
            code = getattr(error, 'status_code', 0) or getattr(error, 'http_status', 0) or 0
        except TypeError:
            code = 0
        if isinstance(code, int) and (code >= 500 or code == 429):
            return True
        return False
    err_str = str(error).lower()
    if any(kw in err_str for kw in ("timeout", "connection", "reset")):
        return True
    return False


def _is_non_retryable(error: Exception) -> bool:
    """判断错误是否不可重试.

    不重试: 400, 401, 403, 404, 模型不存在, 参数非法, schema 非法
    """
    if isinstance(error, (BadRequestError, AuthenticationError,
                          NotFoundError, PermissionDeniedError)):
        return True
    if isinstance(error, (UnprocessableEntityError, ConflictError)):
        return True
    if isinstance(error, APIError):
        try:
            code = getattr(error, 'status_code', 0) or getattr(error, 'http_status', 0) or 0
        except TypeError:
            code = 0
        if isinstance(code, int) and 400 <= code < 500 and code != 429:
            return True
    return False


# ============================================================================
# 统计
# ============================================================================


@dataclass
class ExtractionStats:
    """线程安全的抽取统计."""

    total_chunks: int = 0
    successful_chunks: int = 0
    failed_chunks: int = 0
    total_batches: int = 0
    successful_batches: int = 0
    failed_batches: int = 0
    api_requests: int = 0
    merge_api_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    batch_cache_hits: int = 0
    batch_cache_misses: int = 0
    retries: int = 0
    total_triples_raw: int = 0
    total_triples_after_dedup: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    elapsed_seconds: float = 0.0
    neo4j_write_seconds: float = 0.0
    cost_yuan: float = 0.0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, getattr(self, k) + v)

    def set(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)


# ============================================================================
# 抽取器核心
# ============================================================================


class EntityExtractor:
    """LLM 三元组抽取器."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model_id: str,
        *,
        supports_json_mode: bool = True,
        max_tokens: int = 0,
        temperature: float = 0.1,
        max_retries: int = 0,
        retry_delay: float = 0.0,
        timeout: float = 0.0,
        chunks_per_request: int = 0,
        merge_mode: str = "",
        preset_name: str = "",
        budget_yuan: float = 0.0,
        cache_dir: str = "",
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.model_id = model_id
        self.supports_json_mode = supports_json_mode
        self.max_tokens = max_tokens or MAX_TOKENS
        self.temperature = temperature
        self.max_retries = max_retries if max_retries >= 0 else MAX_RETRIES
        self.retry_delay = retry_delay if retry_delay > 0 else RETRY_DELAY
        self.timeout = timeout if timeout > 0 else TIMEOUT
        self.chunks_per_request = chunks_per_request if chunks_per_request > 0 else CHUNKS_PER_REQUEST
        self.merge_mode = merge_mode or MERGE_MODE
        self.preset_name = preset_name
        self.budget_yuan = budget_yuan
        self.cache_dir = cache_dir or CACHE_DIR

        # OpenAI 客户端: 关闭内部重试，由外层控制
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.api_base,
            timeout=self.timeout,
            max_retries=0,
        )
        self.stats = ExtractionStats()
        self._cache = ExtractionCache(self.cache_dir) if self.cache_dir else None

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_preset(
        cls,
        preset_name: str,
        *,
        api_key: str = "",
        api_base: str = "",
        model_id: str = "",
        **overrides,
    ) -> "EntityExtractor":
        preset = PRESETS.get(preset_name)
        if preset is None:
            raise ValueError(
                f"Unknown preset '{preset_name}'. Available: {', '.join(PRESETS)}"
            )

        resolved_api_key = api_key or _env("LLM_API_KEY")
        resolved_api_base = api_base or _env("LLM_API_BASE")

        if not resolved_api_key:
            raise ValueError("API key required.")
        if not resolved_api_base:
            raise ValueError("API base URL required.")

        kwargs: dict = {
            "api_base": resolved_api_base,
            "api_key": resolved_api_key,
            "model_id": model_id or preset.model_id,
            "supports_json_mode": preset.supports_json_mode,
            "max_tokens": overrides.pop("max_tokens", 0) or preset.max_tokens,
            "temperature": overrides.pop("temperature", 0.1) or preset.temperature,
            "preset_name": preset_name,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    @classmethod
    def from_custom(
        cls, api_base: str, api_key: str, model_id: str, **kwargs
    ) -> "EntityExtractor":
        return cls(api_base=api_base, api_key=api_key, model_id=model_id, **kwargs)

    # ------------------------------------------------------------------
    # 核心: 单 chunk 抽取 (保留兼容)
    # ------------------------------------------------------------------

    def extract_from_chunk(
        self,
        text: str,
        *,
        paper_id: str = "",
        paper_title: str = "",
        chunk_index: int = 0,
        chunk_id: str = "",
        use_cache: bool = True,
    ) -> ExtractionResult:
        """从单个文本块抽取三元组."""
        chunk_sha256 = ExtractionCache.sha256(text)
        cache_key = ""
        retry_count = 0

        # 查缓存
        if use_cache and self._cache:
            cache_key = ExtractionCache.make_key(
                paper_id, chunk_sha256, self.model_id
            )
            cached = self._cache.get(cache_key)
            if cached:
                self.stats.inc(cache_hits=1)
                triples_with_source = []
                for t in cached["triples"]:
                    t.source_chunk_id = chunk_id or f"{paper_id}_chunk_{chunk_index:04d}"
                    t.source_chunk_index = chunk_index
                    triples_with_source.append(t)
                return ExtractionResult(
                    paper_id=paper_id,
                    chunk_index=chunk_index,
                    triples=triples_with_source,
                    raw_response=cached["raw_response"],
                    retry_count=0,
                    cache_hit=True,
                    merge_mode=self.merge_mode,
                )

        self.stats.inc(cache_misses=1, api_requests=1)

        user_prompt = build_user_prompt(
            text,
            paper_title=paper_title,
            chunk_index=chunk_index,
            paper_id=paper_id,
        )
        raw_response, triples, retry_count = self._call_with_retry(user_prompt)

        triples = self._normalize_paper_relations(triples, paper_id)

        # 为每个三元组添加 chunk 来源
        resolved_chunk_id = chunk_id or f"{paper_id}_chunk_{chunk_index:04d}"
        for t in triples:
            t.source_chunk_id = resolved_chunk_id
            t.source_chunk_index = chunk_index
            if resolved_chunk_id not in t.source_chunk_ids:
                t.source_chunk_ids.append(resolved_chunk_id)
            if chunk_index not in t.source_chunk_indices:
                t.source_chunk_indices.append(chunk_index)

        valid_triples = [t for t in triples if self._validate_triple(t)]
        self.stats.inc(successful_chunks=1, total_chunks=1,
                       total_triples_raw=len(valid_triples))

        # 写缓存
        if use_cache and self._cache and raw_response:
            self._cache.put(
                cache_key, raw_response, valid_triples,
                paper_id=paper_id, chunk_index=chunk_index,
                chunk_sha256=chunk_sha256, model_id=self.model_id,
                retry_count=retry_count,
            )

        return ExtractionResult(
            paper_id=paper_id,
            chunk_index=chunk_index,
            triples=valid_triples,
            raw_response=raw_response,
            retry_count=retry_count,
            cache_hit=False,
            merge_mode=self.merge_mode,
        )

    # ------------------------------------------------------------------
    # 批量 chunk 抽取 (重写)
    # ------------------------------------------------------------------

    def extract_sparse_profile(
        self,
        *,
        paper_id: str,
        title: str,
        abstract: str,
        keywords: str = "",
        max_triples: int = 0,
        use_cache: bool = True,
    ) -> BatchedExtractionResult:
        """从标题、摘要和关键词构建稀疏论文关系图。

        这是跨论文图谱的默认入口。全文 chunk 级抽取仍由
        :meth:`extract_from_chunks_batched` 提供，适合 EVIDENCE/FULL_AUDIT，
        但不应作为整库建图的默认流程。
        """
        if not paper_id.strip():
            raise ValueError("paper_id is required for sparse profile extraction")
        if not (title.strip() or abstract.strip() or keywords.strip()):
            raise ValueError("title, abstract, or keywords must contain text")

        # Sparse profile is deliberately bounded: a larger caller value must
        # not silently turn the cross-paper graph back into a full-text graph.
        limit = max(1, min(max_triples or PROFILE_MAX_TRIPLES, 30))
        profile_text = "\n".join(
            part for part in (
                f"title: {title.strip()}" if title.strip() else "",
                f"keywords: {keywords.strip()}" if keywords.strip() else "",
                f"abstract:\n{abstract.strip()}" if abstract.strip() else "",
            ) if part
        )
        profile_hash = ExtractionCache.sha256(profile_text)
        cache_key = ExtractionCache.make_key(
            paper_id,
            profile_hash,
            self.model_id,
            prompt_version=PROFILE_PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )
        t0 = time.monotonic()

        raw_response = ""
        retry_count = 0
        cache_hit = False
        triples: list[Triple]
        if use_cache and self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                raw_response = cached.get("raw_response") or ""
                triples = cached.get("triples", [])
                cache_hit = True
                self.stats.inc(cache_hits=1)
            else:
                triples = []
                self.stats.inc(cache_misses=1)
        else:
            triples = []

        if not cache_hit:
            user_prompt = build_profile_user_prompt(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                keywords=keywords,
            )
            raw_response, triples, retry_count = self._call_with_retry(
                user_prompt,
                system_prompt=PROFILE_SYSTEM_PROMPT,
            )
            self.stats.inc(api_requests=1)

        triples = self._normalize_paper_relations(triples, paper_id)
        valid = [triple for triple in triples if self._validate_triple(triple)]

        # ── L2 稀疏层后处理 ──
        # 1. PRISMA 等报告规范 → ReportingGuideline
        valid = self._tag_prisma_as_guideline(valid)

        # 2. 教学法关系修正: USES_METHOD→PedagogicalMethod ⇒ ADOPTS_PEDAGOGY
        valid = self._fix_pedagogy_relation(valid)

        # 3. Claim tail 名词化: 完整句子 → 名词短语
        for triple in valid:
            if triple.relation == RelationType.CLAIMS.value and triple.tail_type == EntityType.CLAIM.value:
                triple.tail = self._nominalize_claim(triple.tail)

        # 4. L2 层仅保留 Paper→Entity 关系（实体→实体 下沉至 chunk 层）
        valid = self._strip_entity_to_entity(valid, paper_id)

        deduped = self._deduplicate_local(valid)

        # 5. 轻量级跨实体推理：同一论文内高置信度实体对生成 1-2 条 Entity→Entity 关系
        deduped = self._infer_cross_entity_relations(deduped, paper_id)

        selected = self._select_sparse_triples(deduped, limit)
        discarded = len(triples) - len(selected)

        # 6. 最低三元组检查
        min_warnings = self._check_min_triples(selected, paper_id, min_count=PROFILE_MIN_TRIPLES)

        profile_chunk_id = f"{paper_id}_profile"
        for triple in selected:
            triple.source_chunk_id = profile_chunk_id
            triple.source_chunk_index = 0
            if profile_chunk_id not in triple.source_chunk_ids:
                triple.source_chunk_ids.append(profile_chunk_id)
            if 0 not in triple.source_chunk_indices:
                triple.source_chunk_indices.append(0)

        if use_cache and self._cache and not cache_hit and raw_response:
            self._cache.put(
                cache_key,
                raw_response,
                selected,
                paper_id=paper_id,
                chunk_index=0,
                chunk_sha256=profile_hash,
                model_id=self.model_id,
                prompt_version=PROFILE_PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                retry_count=retry_count,
            )

        self.stats.inc(
            total_chunks=1,
            successful_chunks=1,
            total_triples_raw=len(valid),
            total_triples_after_dedup=len(selected),
        )
        elapsed = time.monotonic() - t0
        self.stats.set(elapsed_seconds=self.stats.elapsed_seconds + elapsed)

        return BatchedExtractionResult(
            paper_id=paper_id,
            chunks=[ChunkTriples(
                chunk_id=profile_chunk_id,
                chunk_index=0,
                triples=selected,
                status="success",
            )],
            total_triples=len(selected),
            raw_responses=[raw_response] if raw_response else [],
            batch_count=0 if cache_hit else 1,
            cache_hits=1 if cache_hit else 0,
            cache_misses=0 if cache_hit else 1,
            merge_mode="local",
            retry_count=retry_count,
            elapsed_seconds=elapsed,
            mode="PROFILE",
            max_triples=limit,
            discarded_triples=discarded,
        )

    @staticmethod
    def _select_sparse_triples(
        triples: list[Triple],
        max_triples: int,
    ) -> list[Triple]:
        """按跨论文检索价值排序并限制图谱密度。"""
        relation_priority = {
            RelationType.USES_METHOD.value: 100,
            RelationType.ADOPTS_PEDAGOGY.value: 99,
            RelationType.STUDIES_DOMAIN.value: 98,
            RelationType.DEPLOYS_TECH.value: 96,
            RelationType.INVOLVES_POPULATION.value: 94,
            RelationType.TARGETS_OUTCOME.value: 93,
            RelationType.IMPROVES.value: 91,
            RelationType.INTEGRATES_WITH.value: 88,
            RelationType.COMPARES_WITH.value: 86,
            RelationType.CLAIMS.value: 82,
            RelationType.HAS_SAMPLE.value: 80,
            RelationType.HAS_EFFECT_SIZE.value: 78,
            RelationType.RELATED_TO.value: 20,
        }
        ordered = sorted(
            triples,
            key=lambda triple: (
                -relation_priority.get(triple.relation, 50),
                -triple.confidence,
                triple.head.casefold(),
                triple.tail.casefold(),
            ),
        )
        selected: list[Triple] = []
        related_count = 0
        claim_count = 0
        for triple in ordered:
            if triple.relation == RelationType.RELATED_TO.value:
                if related_count >= PROFILE_MAX_RELATED_TO:
                    continue
                related_count += 1
            if triple.relation == RelationType.CLAIMS.value:
                if claim_count >= PROFILE_MAX_CLAIMS:
                    continue
                claim_count += 1
            selected.append(triple)
            if len(selected) >= max_triples:
                break
        return selected

    @staticmethod
    def _nominalize_claim(text: str) -> str:
        """将 Claim tail 从完整句子转换为名词短语（nominalization）.

        目标转换示例:
          "X effectively visualizes Y" → "effectiveness of X for visualizing Y"
          "AI improves conceptual understanding" → "improvement of conceptual understanding via AI"
          "VR significantly outperforms traditional instruction" → "superiority of VR over traditional instruction"
          "PBL enhances critical thinking and engagement" → "enhanced critical thinking and engagement through PBL"

        规则（按优先级）:
          1. 去掉前导从句引导词
          2. 匹配已知动词→名词转换模式
          3. 通用 SVO → "noun_form of O via S" 回退
          4. 截断 ≤24 词
        """
        if not text or len(text.split()) <= 6:
            return text

        # ── Step 1: 去掉前导从句引导词 ──
        prefixes = [
            r"^(?:the\s+)?(?:results?\s*(?:of\s*)?(?:this\s+)?(?:study|research|review|meta-analysis)\s*"
            r"(?:indicates?|shows?|reveals?|suggests?|found|finds?|demonstrates?)\s*(?:that\s*)?)",
            r"^(?:this\s+(?:study|research|paper|review)\s*)"
            r"(?:found|finds?|indicates?|shows?|suggests?|reveals?|demonstrates?)\s*(?:that\s*)?",
            r"^(?:we\s+(?:found|find|conclude|concluded)\s*(?:that\s*)?)",
            r"^(?:it\s+(?:was|is)\s+(?:found|concluded|observed)\s*(?:that\s*)?)",
            r"^(?:according\s+to\s+(?:the\s+)?(?:results?|findings?|data|analysis)\s*,?\s*)",
            r"^(?:the\s+(?:study|research|analysis|review)\s+)"
            r"(?:found|finds?|indicates?|shows?|suggests?|reveals?|demonstrates?|concludes?)\s*(?:that\s*)?",
        ]
        cleaned = text.strip()
        for pat in prefixes:
            cleaned = re.sub(pat, "", cleaned, count=1, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*\.\s*$", "", cleaned)

        # ── Step 2: 已知动词 → 名词转换 ──
        # 格式: (动词正则, 名词短语模板)
        # 模板中 {S} = 主语, {O} = 宾语, {Ving} = 动名词
        NOMINALIZATION_PATTERNS: list[tuple[str, str]] = [
            # "X improves/enhances/increases/boosts Y" → "improved/enhanced Y via X"
            (
                r"^(.+?)\s+(?:significantly\s+)?(?:greatly\s+)?(improves?|enhances?|increases?|boosts?|strengthens?)\s+(.+)$",
                r"enhanced \3 via \1",
            ),
            # "X reduces/decreases/lowers Y" → "reduction of Y via X"
            (
                r"^(.+?)\s+(?:significantly\s+)?(reduces?|decreases?|lowers?|diminishes?)\s+(.+)$",
                r"reduction of \3 via \1",
            ),
            # "X is effective/beneficial for Y" → "effectiveness of X for Y"
            (
                r"^(.+?)\s+is\s+(effective|beneficial|useful|valuable)\s+(?:for|in|at)\s+(.+)$",
                r"effectiveness of \1 for \3",
            ),
            # "X outperforms Y (on Z)" → "superiority of X over Y"
            (
                r"^(.+?)\s+(?:significantly\s+)?outperforms?\s+(.+?)(?:\s+on\s+.+)?$",
                r"superiority of \1 over \2",
            ),
            # "X positively/negatively affects/influences/impacts Y" → "effect of X on Y"
            (
                r"^(.+?)\s+(?:positively|negatively|significantly|moderately|strongly)\s+(affects?|influences?|impacts?)\s+(.+)$",
                r"effect of \1 on \3",
            ),
            # "X shows/demonstrates/exhibits (a) Y effect on Z" → "Y effect of X on Z"
            (
                r"^(.+?)\s+(?:shows?|demonstrates?|exhibits?)\s+(?:a|an)?\s*(moderate|large|small|significant|positive|negative|strong|weak)\s+(effect|impact|influence)\s+(?:on|upon)\s+(.+)$",
                r"\1: \2 \3 on \4",
            ),
            # "X supports/facilitates/helps/enables/promotes Y" → "X as facilitator of Y"
            (
                r"^(.+?)\s+(?:effectively\s+)?(supports?|facilitates?|helps?|enables?|promotes?)\s+(.+)$",
                r"\1 as facilitator of \3",
            ),
            # "X is (particularly) effective/suitable for Y" → "suitability of X for Y"
            (
                r"^(.+?)\s+is\s+(?:particularly\s+)?(effective|suitable|appropriate|useful)\s+(?:for|in|at)\s+(.+)$",
                r"suitability of \1 for \3",
            ),
            # "X can improve/enhance Y" → "potential of X to improve Y"
            (
                r"^(.+?)\s+can\s+(improve|enhance|increase|reduce|facilitate|support|help)\s+(.+)$",
                r"potential of \1 to \2 \3",
            ),
            # "X leads to / results in Y" → "X leading to Y"
            (
                r"^(.+?)\s+leads?\s+to\s+(.+)$",
                r"\1 as driver of \2",
            ),
            # "X is associated with Y" → "association between X and Y"
            (
                r"^(.+?)\s+is\s+(?:positively|negatively|significantly|strongly)?\s*associated\s+with\s+(.+)$",
                r"association between \1 and \2",
            ),
            # "X contributes to Y" → "contribution of X to Y"
            (
                r"^(.+?)\s+contributes?\s+to\s+(.+)$",
                r"contribution of \1 to \2",
            ),
            # "No significant difference between X and Y" → "comparable X and Y"
            (
                r"^(?:no|without)\s+(?:significant\s+)?difference\s+(?:between|among)\s+(.+?)\s+and\s+(.+)$",
                r"comparable outcomes: \1 vs \2",
            ),
        ]

        for pattern, template in NOMINALIZATION_PATTERNS:
            m = re.match(pattern, cleaned, re.IGNORECASE)
            if m:
                result = template
                for gi in range(1, len(m.groups()) + 1):
                    result = result.replace(f"\\{gi}", m.group(gi).strip())
                # Clean up double spaces and trailing punctuation
                result = re.sub(r"\s{2,}", " ", result).strip()
                result = re.sub(r"\s*\.\s*$", "", result)
                if 6 <= len(result.split()) <= MAX_ENTITY_WORDS:
                    return result
                # If too long, truncate
                words = result.split()
                if len(words) > MAX_ENTITY_WORDS:
                    result = " ".join(words[:MAX_ENTITY_WORDS]) + " ..."
                return result

        # ── Step 3: 通用 SVO 回退（仅当文本看起来像完整从句时才尝试）──
        # 判断是否已经是名词短语：含 "of"/"via"/"through"/"by"/"for" 结构标记且无助动词
        already_nominalized = bool(
            re.search(r"\b(?:of|via|through|by)\s+\w+", cleaned, re.IGNORECASE)
            and not re.search(r"\b(?:is|are|was|were|has|have|had|will|would|can|could|may|might|should)\b", cleaned, re.IGNORECASE)
        )
        # 判断是否为从句：含助动词或系动词
        aux_verbs = r"\b(?:is|are|was|were|has|have|had|will|would|can|could|may|might|should|does|do|did)\b"
        looks_like_clause = bool(re.search(aux_verbs, cleaned, re.IGNORECASE))
        if not already_nominalized and looks_like_clause and len(cleaned.split()) >= 8:
            generic_svo = re.match(
                r"^(.+?)\s+(?:significantly|greatly|strongly|moderately|positively|negatively|effectively)?\s*"
                r"(\w+(?:s|es|ed|ing)?)\s+(.+)$",
                cleaned, re.IGNORECASE,
            )
            if generic_svo:
                subj, verb, obj = generic_svo.group(1).strip(), generic_svo.group(2).strip(), generic_svo.group(3).strip()
                # 简单动词→名词规则
                verb_noun_map = {
                    "improves": "improvement", "improve": "improvement", "improved": "improvement",
                    "enhances": "enhancement", "enhance": "enhancement", "enhanced": "enhancement",
                    "increases": "increase", "increase": "increase", "increased": "increase",
                    "reduces": "reduction", "reduce": "reduction", "reduced": "reduction",
                    "affects": "effect", "affect": "effect", "affected": "effect",
                    "influences": "influence", "influence": "influence", "influenced": "influence",
                    "develops": "development", "develop": "development",
                    "supports": "support", "support": "support",
                    "promotes": "promotion", "promote": "promotion",
                    "facilitates": "facilitation", "facilitate": "facilitation",
                    "enables": "enablement", "enable": "enablement",
                    "outperforms": "superiority", "outperform": "superiority",
                    "shows": "demonstration", "show": "demonstration",
                    "predicts": "prediction", "predict": "prediction",
                    "indicates": "indication", "indicate": "indication",
                    "reveals": "revelation", "reveal": "revelation",
                    "transforms": "transformation", "transform": "transformation",
                    "integrates": "integration", "integrate": "integration",
                    "fosters": "fostering", "foster": "fostering",
                    "helps": "assistance", "help": "assistance",
                }
                verb_lower = verb.lower().rstrip("s").rstrip("ed").rstrip("ing")
                noun_form = verb_noun_map.get(verb.lower(), verb_lower + "ing")
                result = f"{noun_form} of {obj} via {subj}"
                result = re.sub(r"\s{2,}", " ", result).strip()
                words = result.split()
                if len(words) >= 6:
                    if len(words) > MAX_ENTITY_WORDS:
                        result = " ".join(words[:MAX_ENTITY_WORDS]) + " ..."
                    return result

        # ── Step 4: 截断 ──
        words = cleaned.split()
        if len(words) > MAX_ENTITY_WORDS:
            cleaned = " ".join(words[:MAX_ENTITY_WORDS]) + " ..."

        return cleaned.strip() or text.split(".")[0].strip()[:MAX_ENTITY_CHARS]

    @staticmethod
    def _strip_entity_to_entity(triples: list[Triple], paper_id: str) -> list[Triple]:
        """从 L2 稀疏层移除非论文级关系（实体→实体 下沉至 chunk 层）。

        L2 稀疏层仅保留 Paper→Entity 的关系。
        IMPROVES / INTEGRATES_WITH / COMPARES_WITH 等在 L2 层
        也需要 Paper 作为 head（通过 CLAIMS 间接表达），直接
        的 entity→entity 关系留待全文 chunk 层抽取。
        """
        kept: list[Triple] = []
        for t in triples:
            if t.head_type == EntityType.PAPER.value:
                kept.append(t)
                continue
            # 非 Paper head 的关系在 L2 稀疏层中丢弃
            # （这些关系留给 chunk 级 FULL_AUDIT 模式处理）
        return kept

    @staticmethod
    def _infer_cross_entity_relations(
        triples: list[Triple],
        paper_id: str,
    ) -> list[Triple]:
        """轻量级跨实体推理：同一论文内高置信度实体对生成 1-2 条 Entity→Entity 关系.

        目的：避免图谱退化为纯星型结构（只有 Paper→Entity），补充少量
        实体间边以支持多跳导航。

        规则（按优先级）：
          1. Technology → LearningOutcome (IMPROVES) — 最通用
          2. Technology ↔ PedagogicalMethod (INTEGRATES_WITH) — 双向
          3. PedagogicalMethod → LearningOutcome (IMPROVES)

        约束：
          - 最多添加 2 条跨实体关系
          - 实体 confidence ≥ 0.85
          - 关系 confidence 取 min(parent_confidences) × 0.85
          - evidence 合并自双方原始 evidence
        """
        # 收集按类型分组的实体及其 confidence 和 evidence
        entities_by_type: dict[str, list[tuple[str, float, str]]] = {}
        for t in triples:
            if t.head_type != EntityType.PAPER.value:
                continue
            if t.confidence < 0.85:
                continue
            tail_type = t.tail_type
            if tail_type not in entities_by_type:
                entities_by_type[tail_type] = []
            entities_by_type[tail_type].append((t.tail, t.confidence, t.evidence))

        techs = entities_by_type.get(EntityType.TECHNOLOGY.value, [])
        pedagogies = entities_by_type.get(EntityType.PEDAGOGICAL_METHOD.value, [])
        outcomes = entities_by_type.get(EntityType.LEARNING_OUTCOME.value, [])
        comparisons = entities_by_type.get(EntityType.COMPARISON_CONDITION.value, [])

        inferred: list[Triple] = []
        max_infer = 2

        # Rule 1: Technology → LearningOutcome (IMPROVES)
        for tech_name, tech_conf, tech_ev in techs:
            if len(inferred) >= max_infer:
                break
            for out_name, out_conf, out_ev in outcomes:
                if len(inferred) >= max_infer:
                    break
                if tech_name.lower().strip() == out_name.lower().strip():
                    continue
                conf = round(min(tech_conf, out_conf) * 0.85, 2)
                evidence = EntityExtractor._join_evidence(tech_ev, out_ev)
                inferred.append(Triple(
                    head=tech_name, head_type=EntityType.TECHNOLOGY.value,
                    relation=RelationType.IMPROVES.value,
                    tail=out_name, tail_type=EntityType.LEARNING_OUTCOME.value,
                    evidence=evidence,
                    confidence=conf,
                    layer="L2",
                    source_chunk_id=f"{paper_id}_profile",
                    source_chunk_index=0,
                ))

        # Rule 2: Technology ↔ PedagogicalMethod (INTEGRATES_WITH)
        for tech_name, tech_conf, tech_ev in techs:
            if len(inferred) >= max_infer:
                break
            for ped_name, ped_conf, ped_ev in pedagogies:
                if len(inferred) >= max_infer:
                    break
                if tech_name.lower().strip() == ped_name.lower().strip():
                    continue
                conf = round(min(tech_conf, ped_conf) * 0.85, 2)
                evidence = EntityExtractor._join_evidence(tech_ev, ped_ev)
                inferred.append(Triple(
                    head=tech_name, head_type=EntityType.TECHNOLOGY.value,
                    relation=RelationType.INTEGRATES_WITH.value,
                    tail=ped_name, tail_type=EntityType.PEDAGOGICAL_METHOD.value,
                    evidence=evidence,
                    confidence=conf,
                    layer="L2",
                    source_chunk_id=f"{paper_id}_profile",
                    source_chunk_index=0,
                ))

        # Rule 3: PedagogicalMethod → LearningOutcome (IMPROVES)
        for ped_name, ped_conf, ped_ev in pedagogies:
            if len(inferred) >= max_infer:
                break
            for out_name, out_conf, out_ev in outcomes:
                if len(inferred) >= max_infer:
                    break
                if ped_name.lower().strip() == out_name.lower().strip():
                    continue
                conf = round(min(ped_conf, out_conf) * 0.85, 2)
                evidence = EntityExtractor._join_evidence(ped_ev, out_ev)
                inferred.append(Triple(
                    head=ped_name, head_type=EntityType.PEDAGOGICAL_METHOD.value,
                    relation=RelationType.IMPROVES.value,
                    tail=out_name, tail_type=EntityType.LEARNING_OUTCOME.value,
                    evidence=evidence,
                    confidence=conf,
                    layer="L2",
                    source_chunk_id=f"{paper_id}_profile",
                    source_chunk_index=0,
                ))

        # Rule 4: Technology → ComparisonCondition (COMPARES_WITH)
        for tech_name, tech_conf, tech_ev in techs:
            if len(inferred) >= max_infer:
                break
            for comp_name, comp_conf, comp_ev in comparisons:
                if len(inferred) >= max_infer:
                    break
                if tech_name.lower().strip() == comp_name.lower().strip():
                    continue
                conf = round(min(tech_conf, comp_conf) * 0.85, 2)
                evidence = EntityExtractor._join_evidence(tech_ev, comp_ev)
                inferred.append(Triple(
                    head=tech_name, head_type=EntityType.TECHNOLOGY.value,
                    relation=RelationType.COMPARES_WITH.value,
                    tail=comp_name, tail_type=EntityType.COMPARISON_CONDITION.value,
                    evidence=evidence,
                    confidence=conf,
                    layer="L3",
                    source_chunk_id=f"{paper_id}_profile",
                    source_chunk_index=0,
                ))

        return triples + inferred

    @staticmethod
    def _tag_prisma_as_guideline(triples: list[Triple]) -> list[Triple]:
        """将 PRISMA 等报告规范从 ResearchMethod 迁移至 ReportingGuideline."""
        guideline_keywords = {
            "prisma", "strobe", "consort", "moose", "starlite",
            "preferred reporting items", "strengthening the reporting",
        }
        for t in triples:
            name_lower = t.tail.strip().lower()
            if any(kw in name_lower for kw in guideline_keywords):
                if t.tail_type == EntityType.RESEARCH_METHOD.value:
                    t.tail_type = EntityType.REPORTING_GUIDELINE.value
        return triples

    @staticmethod
    def _fix_pedagogy_relation(triples: list[Triple]) -> list[Triple]:
        """教学法关系修正：tail_type==PedagogicalMethod 必须用 ADOPTS_PEDAGOGY.

        规则：
        1. USES_METHOD + PedagogicalMethod → ADOPTS_PEDAGOGY + PedagogicalMethod
        2. 其他 relation + PedagogicalMethod (非 Paper head) → 不变
        3. ADOPTS_PEDAGOGY + 非 PedagogicalMethod → USES_METHOD (反向修正)
        """
        for t in triples:
            if t.relation == RelationType.USES_METHOD.value:
                if t.tail_type == EntityType.PEDAGOGICAL_METHOD.value:
                    t.relation = RelationType.ADOPTS_PEDAGOGY.value
            elif t.relation == RelationType.ADOPTS_PEDAGOGY.value:
                if t.tail_type != EntityType.PEDAGOGICAL_METHOD.value:
                    # 反向修正：ADOPTS_PEDAGOGY 的 tail 不是教学法 → 改回 USES_METHOD
                    t.relation = RelationType.USES_METHOD.value
        return triples

    @staticmethod
    def _join_evidence(existing: str, new: str) -> str:
        """拼接 evidence，非连续片段使用 [...] 分隔。"""
        if not existing:
            return new
        if not new or new in existing:
            return existing
        return f"{existing} [...] {new}"

    @staticmethod
    def _check_min_triples(
        selected: list[Triple],
        paper_id: str,
        *,
        min_count: int = 8,
    ) -> list[str]:
        """检查是否有遗漏的关键维度，返回补充建议列表。"""
        covered = {t.relation for t in selected}
        suggestions: list[str] = []
        # 关键维度检查
        if "USES_METHOD" not in covered and "ADOPTS_PEDAGOGY" not in covered:
            suggestions.append("USES_METHOD/ADOPTS_PEDAGOGY: 是否遗漏了研究方法/教学法/报告规范?")
        if "STUDIES_DOMAIN" not in covered:
            suggestions.append("STUDIES_DOMAIN: 是否遗漏了学科领域?")
        if "INVOLVES_POPULATION" not in covered:
            suggestions.append("INVOLVES_POPULATION: 是否遗漏了学生群体?")
        if "TARGETS_OUTCOME" not in covered:
            suggestions.append("TARGETS_OUTCOME: 是否遗漏了学习成果?")
        if "DEPLOYS_TECH" not in covered:
            suggestions.append("DEPLOYS_TECH: 是否遗漏了技术/工具?")
        if "HAS_SAMPLE" not in covered:
            suggestions.append("HAS_SAMPLE: 是否遗漏了样本信息?")
        if len(selected) < min_count:
            suggestions.insert(
                0,
                f"三元组数量 ({len(selected)}) 低于最低阈值 ({min_count})，需要补充抽取",
            )
        return suggestions

    def extract_from_chunks_batched(
        self,
        chunks: list[str],
        *,
        paper_id: str = "",
        paper_title: str = "",
        batch_size: int = 0,
        use_cache: bool = True,
        max_workers: int = 0,
    ) -> BatchedExtractionResult:
        """批量抽取: 多个 chunk 合并为一次 API 请求.

        每个三元组保留 source_chunk_id 和 source_chunk_index。
        返回 BatchedExtractionResult 含完整溯源信息。

        Args:
            chunks: 文本块列表
            paper_id: 论文 ID
            paper_title: 论文标题
            batch_size: 每批 chunk 数 (0=使用默认)
            use_cache: 是否使用缓存
            max_workers: 并发 worker 数 (0=使用默认)
        """
        t0 = time.monotonic()
        bs = batch_size or self.chunks_per_request
        bs = max(1, min(bs, 8))  # 限制 1-8
        n_chunks = len(chunks)
        self.stats.inc(total_chunks=n_chunks)

        # 构建带 ID 的 chunk 列表
        chunk_items = [
            {
                "chunk_id": f"{paper_id}_chunk_{i:04d}",
                "chunk_index": i,
                "text": text,
                "sha256": ExtractionCache.sha256(text),
            }
            for i, text in enumerate(chunks)
        ]

        # ── 第一阶段：构建批量批次 ──
        all_batches = [
            chunk_items[i:i + bs]
            for i in range(0, len(chunk_items), bs)
        ]
        self.stats.inc(total_batches=len(all_batches))

        # ── 第二阶段：批量预读缓存 ──
        all_batch_keys: list[str] = []
        batch_key_to_idx: dict[str, int] = {}
        for batch_idx, batch in enumerate(all_batches):
            ordered_sha256s = [item["sha256"] for item in batch]
            bk = ExtractionCache.make_batch_key(
                paper_id, ordered_sha256s, self.model_id, bs,
                batch_prompt_version=BATCH_PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
            )
            all_batch_keys.append(bk)
            batch_key_to_idx[bk] = batch_idx

        cached_batch_results: dict[int, list[ChunkTriples]] = {}
        raw_responses_map: dict[int, str] = {}  # batch_idx → raw_response
        pending_batch_indices: list[int] = []
        batch_key_map: dict[int, str] = {}  # batch_idx → batch_key

        if use_cache and self._cache:
            preloaded = self._cache.preload_batch_cache(all_batch_keys)
            for bk, batch_idx in batch_key_to_idx.items():
                batch_key_map[batch_idx] = bk
                if preloaded.get(bk):
                    chunk_results = preloaded[bk]["chunk_results"]
                    # 恢复 chunk 来源信息
                    for cr in chunk_results:
                        for t in cr.triples:
                            t.source_chunk_id = cr.chunk_id
                            t.source_chunk_index = cr.chunk_index
                            if cr.chunk_id not in t.source_chunk_ids:
                                t.source_chunk_ids.append(cr.chunk_id)
                            if cr.chunk_index not in t.source_chunk_indices:
                                t.source_chunk_indices.append(cr.chunk_index)
                    cached_batch_results[batch_idx] = chunk_results
                    if preloaded[bk].get("raw_response"):
                        raw_responses_map[batch_idx] = preloaded[bk]["raw_response"]
                    self.stats.inc(batch_cache_hits=1, cache_hits=len(chunk_results))
                else:
                    pending_batch_indices.append(batch_idx)
                    self.stats.inc(batch_cache_misses=1, cache_misses=len(all_batches[batch_idx]))
        else:
            pending_batch_indices = list(range(len(all_batches)))
            for batch_idx in range(len(all_batches)):
                bk = all_batch_keys[batch_idx]
                batch_key_map[batch_idx] = bk
            self.stats.inc(cache_misses=n_chunks)

        # ── 第三阶段：对 cache-miss 的 batch 进行 API 抽取 ──
        batch_results_map: dict[int, list[ChunkTriples]] = {}
        failures: list[BatchFailure] = []
        workers = max_workers if max_workers > 0 else MAX_WORKERS
        workers = max(1, min(workers, len(pending_batch_indices))) if pending_batch_indices else 1

        if pending_batch_indices:
            if workers > 1 and len(pending_batch_indices) > 1:
                from concurrent.futures import ThreadPoolExecutor, as_completed

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    fut_map = {}
                    for batch_idx in pending_batch_indices:
                        batch = all_batches[batch_idx]
                        bk = batch_key_map[batch_idx]
                        future = executor.submit(
                            self._process_one_batch_safe,
                            batch, batch_idx, paper_id, paper_title,
                            use_cache, bk, bs,
                        )
                        fut_map[future] = batch_idx

                    for future in as_completed(fut_map):
                        batch_idx = fut_map[future]
                        try:
                            chunk_results, failure, raw_resp = future.result()
                            if raw_resp:
                                raw_responses_map[batch_idx] = raw_resp
                            if failure:
                                failures.append(failure)
                                self.stats.inc(failed_batches=1)
                            else:
                                batch_results_map[batch_idx] = chunk_results
                                self.stats.inc(successful_batches=1)
                        except Exception as e:
                            batch = all_batches[batch_idx]
                            failures.append(BatchFailure(
                                batch_index=batch_idx,
                                chunk_indices=[item["chunk_index"] for item in batch],
                                status="failed",
                                error_type="execution_error",
                                error_message=str(e),
                                retry_count=0,
                            ))
                            self.stats.inc(failed_batches=1)
            else:
                for batch_idx in pending_batch_indices:
                    batch = all_batches[batch_idx]
                    bk = batch_key_map[batch_idx]
                    try:
                        chunk_results, failure, raw_resp = self._process_one_batch_safe(
                            batch, batch_idx, paper_id, paper_title,
                            use_cache, bk, bs,
                        )
                        if raw_resp:
                            raw_responses_map[batch_idx] = raw_resp
                        if failure:
                            failures.append(failure)
                            self.stats.inc(failed_batches=1)
                        else:
                            batch_results_map[batch_idx] = chunk_results
                            self.stats.inc(successful_batches=1)
                    except Exception as e:
                        failures.append(BatchFailure(
                            batch_index=batch_idx,
                            chunk_indices=[item["chunk_index"] for item in batch],
                            status="failed",
                            error_type="execution_error",
                            error_message=str(e),
                            retry_count=0,
                        ))
                        self.stats.inc(failed_batches=1)

        # ── 第四阶段：合并结果（按 batch_index 稳定排序） ──
        all_chunk_results: list[ChunkTriples] = []

        # 先加入缓存的 batch 结果
        for batch_idx in sorted(cached_batch_results):
            all_chunk_results.extend(cached_batch_results[batch_idx])

        # 再加入 API 返回的 batch 结果
        for batch_idx in sorted(batch_results_map):
            all_chunk_results.extend(batch_results_map[batch_idx])

        # 对失败的 chunk 创建空的 ChunkTriples 记录
        failed_chunk_indices: set[int] = set()
        for failure in failures:
            for ci in failure.chunk_indices:
                failed_chunk_indices.add(ci)

        for item in chunk_items:
            ci = item["chunk_index"]
            already_covered = any(cr.chunk_index == ci for cr in all_chunk_results)
            if not already_covered:
                all_chunk_results.append(ChunkTriples(
                    chunk_id=item["chunk_id"],
                    chunk_index=ci,
                    triples=[],
                    status="failed",
                    error_message="Batch failed: chunk not processed",
                ))

        # 按 chunk_index 排序
        all_chunk_results.sort(key=lambda cr: cr.chunk_index)

        # ── 第五阶段：本地去重 ──
        all_triples: list[Triple] = []
        for cr in all_chunk_results:
            all_triples.extend(cr.triples)

        if self.merge_mode == "llm" and len(all_triples) > 1:
            merged = self._merge_triples_llm(all_triples)
            self.stats.inc(merge_api_requests=1)
        else:
            merged = self._deduplicate_local(all_triples)

        self.stats.inc(total_triples_after_dedup=len(merged))

        elapsed = time.monotonic() - t0
        self.stats.set(elapsed_seconds=self.stats.elapsed_seconds + elapsed)

        # 更新成功/失败计数
        success_count = sum(1 for cr in all_chunk_results if cr.status == "success")
        fail_count = sum(1 for cr in all_chunk_results if cr.status == "failed")
        self.stats.inc(successful_chunks=success_count, failed_chunks=fail_count)

        # 按 batch_index 排序 raw_responses
        sorted_raw_responses = [
            raw_responses_map[idx]
            for idx in sorted(raw_responses_map)
        ]

        return BatchedExtractionResult(
            paper_id=paper_id,
            chunks=all_chunk_results,
            total_triples=len(merged),
            raw_responses=sorted_raw_responses,
            batch_count=len(pending_batch_indices),
            cache_hits=sum(1 for _ in cached_batch_results for __ in cached_batch_results[_]),
            cache_misses=sum(len(all_batches[idx]) for idx in pending_batch_indices),
            failures=failures,
            merge_mode=self.merge_mode,
            retry_count=sum(f.retry_count for f in failures),
            elapsed_seconds=elapsed,
        )

    def _process_one_batch_safe(
        self,
        batch: list[dict],
        batch_idx: int,
        paper_id: str,
        paper_title: str,
        use_cache: bool,
        batch_cache_key: str,
        batch_size: int,
    ) -> tuple[list[ChunkTriples], Optional[BatchFailure], str]:
        """处理一个批量请求 —— 安全版本，失败不抛异常.

        Returns:
            (chunk_results, failure_or_None, raw_response)
        """
        total_retries = 0
        raw_response = ""
        chunk_indices = [item["chunk_index"] for item in batch]

        try:
            user_prompt = build_batch_user_prompt(
                batch,
                paper_title=paper_title,
                paper_id=paper_id,
            )
            raw_response, triples, attempt_retries = self._call_with_retry(user_prompt)
            total_retries = attempt_retries

            # 解析批量响应
            extracted = self._parse_batch_response(raw_response, batch)
            for chunk_triples in extracted.values():
                self._normalize_paper_relations(chunk_triples, paper_id)

            # 检查是否有 chunk 缺少合法的 chunk_id 匹配
            matched_chunk_indices = set(extracted.keys())
            expected_chunk_indices = {item["chunk_index"] for item in batch}
            missing_indices = expected_chunk_indices - matched_chunk_indices
            extra_indices = matched_chunk_indices - expected_chunk_indices

            if missing_indices:
                # 任何缺失的 expected chunk_id → provenance 校验失败
                # 尝试重试一次
                self.stats.inc(retries=1)
                total_retries += 1
                raw_response2, triples2, retry_count2 = self._call_with_retry(user_prompt)
                total_retries += retry_count2
                extracted2 = self._parse_batch_response(raw_response2, batch)
                for chunk_triples in extracted2.values():
                    self._normalize_paper_relations(chunk_triples, paper_id)

                matched2 = set(extracted2.keys())
                missing2 = expected_chunk_indices - matched2

                if not missing2:
                    # 重试成功 —— 所有 chunk 都有匹配
                    extracted = extracted2
                    raw_response = raw_response2
                else:
                    # 重试仍失败 —— 确定 error_type
                    if extra_indices:
                        error_type = "invalid_chunk_id"
                        error_msg = (
                            f"Batch {batch_idx}: response contains unrecognized chunk_ids. "
                            f"Missing: {sorted(missing_indices)}, "
                            f"Extra/unknown: {sorted(extra_indices)}"
                        )
                    else:
                        error_type = "missing_chunk_mapping"
                        error_msg = (
                            f"Batch {batch_idx}: response missing chunk_ids "
                            f"{sorted(missing_indices)} after retry. "
                            f"Cannot establish provenance for {len(missing_indices)} chunks."
                        )

                    failure = BatchFailure(
                        batch_index=batch_idx,
                        chunk_indices=chunk_indices,
                        status="failed",
                        error_type=error_type,
                        error_message=error_msg,
                        retry_count=total_retries,
                        raw_response_snippet=raw_response2[:500] if raw_response2 else raw_response[:500],
                    )
                    # 为缺失的 chunk 创建失败记录
                    failed_results: list[ChunkTriples] = []
                    for item in batch:
                        ci = item["chunk_index"]
                        if ci in missing2:
                            failed_results.append(ChunkTriples(
                                chunk_id=item["chunk_id"],
                                chunk_index=ci,
                                triples=[],
                                status="failed",
                                error_message=f"Missing chunk_id mapping: {error_type}",
                            ))
                        else:
                            chunk_triples = extracted.get(ci, [])
                            for t in chunk_triples:
                                t.source_chunk_id = item["chunk_id"]
                                t.source_chunk_index = ci
                                if item["chunk_id"] not in t.source_chunk_ids:
                                    t.source_chunk_ids.append(item["chunk_id"])
                                if ci not in t.source_chunk_indices:
                                    t.source_chunk_indices.append(ci)
                            valid = [t for t in chunk_triples if self._validate_triple(t)]
                            failed_results.append(ChunkTriples(
                                chunk_id=item["chunk_id"],
                                chunk_index=ci,
                                triples=valid,
                                status="success",
                            ))
                    return failed_results, failure, raw_response2 or raw_response

            # 全部 chunk 匹配成功
            chunk_results: list[ChunkTriples] = []
            for item in batch:
                ci = item["chunk_index"]
                chunk_triples = extracted.get(ci, [])
                # 为每个三元组标注 chunk 来源
                for t in chunk_triples:
                    t.source_chunk_id = item["chunk_id"]
                    t.source_chunk_index = ci
                    if item["chunk_id"] not in t.source_chunk_ids:
                        t.source_chunk_ids.append(item["chunk_id"])
                    if ci not in t.source_chunk_indices:
                        t.source_chunk_indices.append(ci)

                valid = [t for t in chunk_triples if self._validate_triple(t)]
                chunk_results.append(ChunkTriples(
                    chunk_id=item["chunk_id"],
                    chunk_index=ci,
                    triples=valid,
                    status="success",
                ))

            # 写入批量缓存（仅成功 batch）
            if use_cache and self._cache and raw_response:
                chunk_sha256s = [item["sha256"] for item in batch]
                self._cache.put_batch(
                    batch_cache_key, raw_response, chunk_results,
                    paper_id=paper_id, chunk_sha256s=chunk_sha256s,
                    model_id=self.model_id, batch_size=batch_size,
                    batch_prompt_version=BATCH_PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                    retry_count=total_retries,
                )

            return chunk_results, None, raw_response

        except ExtractionError as e:
            # 结构化的提取错误 — retry_count 来自实际重试
            failure = BatchFailure(
                batch_index=batch_idx,
                chunk_indices=chunk_indices,
                status="failed",
                error_type=e.error_type if e.error_type != "max_retries" else "max_retries",
                error_message=str(e),
                retry_count=total_retries,
                raw_response_snippet=raw_response[:500] if raw_response else "",
            )
            return [], failure, raw_response
        except Exception as e:
            failure = BatchFailure(
                batch_index=batch_idx,
                chunk_indices=chunk_indices,
                status="failed",
                error_type="unknown_error",
                error_message=str(e),
                retry_count=total_retries,
                raw_response_snippet=raw_response[:500] if raw_response else "",
            )
            return [], failure, raw_response

    def _parse_batch_response(
        self, raw: str, batch: list[dict]
    ) -> dict[int, list[Triple]]:
        """解析批量抽取的 JSON 响应.

        只接受明确的 chunk_id 匹配，不猜测来源。

        Returns: {chunk_index: [Triple, ...]}
        """
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            return {}

        if isinstance(data, dict) and "results" in data:
            results: dict[int, list[Triple]] = {}
            chunk_id_to_index = {b["chunk_id"]: b["chunk_index"] for b in batch}

            for item in data["results"]:
                chunk_id = item.get("chunk_id", "")
                chunk_triples = item.get("triples", [])

                # 只接受明确的 chunk_id 匹配
                if chunk_id not in chunk_id_to_index:
                    # chunk_id 不匹配任何已知 chunk — 跳过
                    continue

                ci = chunk_id_to_index[chunk_id]
                try:
                    parsed = [
                        Triple(**t) for t in chunk_triples
                        if isinstance(t, dict)
                    ]
                except Exception:
                    continue
                results[ci] = parsed

            return results

        return {}

    # ------------------------------------------------------------------
    # 原有: 多 chunk 分别抽取 (保留兼容)
    # ------------------------------------------------------------------

    def extract_from_chunks(
        self,
        chunks: list[str],
        *,
        paper_id: str = "",
        paper_title: str = "",
        merge: bool = True,
        max_workers: int = 0,
        use_cache: bool = True,
    ) -> ExtractionResult:
        """从多个文本块分别抽取并合并.

        Args:
            merge: 是否去重
            max_workers: 并发数 (0=环境变量默认)
            use_cache: 是否使用缓存
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        t0 = time.monotonic()
        n = len(chunks)
        self.stats.inc(total_chunks=n)

        workers = max_workers if max_workers > 0 else MAX_WORKERS
        workers = max(1, min(workers, n))

        all_triples: list[Triple] = []
        raw_responses: list[str] = []

        if workers > 1 and n > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        self.extract_from_chunk,
                        chunk, paper_id=paper_id, paper_title=paper_title,
                        chunk_index=i, use_cache=use_cache,
                    ): i
                    for i, chunk in enumerate(chunks)
                }
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        all_triples.extend(result.triples)
                        if result.raw_response:
                            raw_responses.append(result.raw_response)
                    except Exception:
                        self.stats.inc(failed_chunks=1)
            self.stats.inc(successful_chunks=n)
        else:
            for i, chunk in enumerate(chunks):
                try:
                    result = self.extract_from_chunk(
                        chunk, paper_id=paper_id, paper_title=paper_title,
                        chunk_index=i, use_cache=use_cache,
                    )
                    all_triples.extend(result.triples)
                    if result.raw_response:
                        raw_responses.append(result.raw_response)
                except Exception:
                    self.stats.inc(failed_chunks=1)

        # 去重合并 — 默认 local，只有显式 merge_mode='llm' 才调用 LLM
        if merge and len(all_triples) > 1:
            if self.merge_mode == "llm":
                merged = self._merge_triples_llm(all_triples)
                self.stats.inc(merge_api_requests=1)
            else:
                merged = self._deduplicate_local(all_triples)
        else:
            merged = self._deduplicate_local(all_triples)

        self.stats.inc(total_triples_after_dedup=len(merged))
        self.stats.set(elapsed_seconds=self.stats.elapsed_seconds + time.monotonic() - t0)

        return ExtractionResult(
            paper_id=paper_id,
            chunk_index=-1,
            triples=merged,
            raw_response="\n---\n".join(raw_responses) if raw_responses else None,
            merge_mode=self.merge_mode,
        )

    # ------------------------------------------------------------------
    # LLM 调用 (含智能重试)
    # ------------------------------------------------------------------

    def _call_with_retry(
        self,
        user_prompt: str,
        *,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> tuple[str, list[Triple], int]:
        """调用 LLM 并解析，带选择性重试.

        只对以下错误重试:
          - timeout
          - connection error
          - 429
          - 500-599
          - 明确的 JSON 解析错误

        以下错误不重试:
          - 400, 401, 403, 404
          - 模型不存在
          - 参数非法
        """
        last_error: Optional[Exception] = None
        raw_response = ""
        triples: list[Triple] = []

        for attempt in range(self.max_retries + 1):
            try:
                raw_response, triples = self._call_llm(
                    user_prompt,
                    system_prompt=system_prompt,
                )
                # 如果解析结果为空且是 JSON 解析问题，触发重试
                if not triples and raw_response.strip():
                    raise ValueError("JSON parse error: empty triples from non-empty response")
                return raw_response, triples, attempt
            except ExtractionError:
                # 非重试错误，直接向上抛
                raise
            except Exception as e:
                last_error = e
                # 不可重试的错误立即抛出
                if _is_non_retryable(e):
                    raise ExtractionError(
                        f"Non-retryable error: {e}",
                        error_type="non_retryable",
                        status_code=getattr(e, 'status_code', 0),
                    )
                # 可重试
                if _is_retryable(e) or "JSON" in str(e).upper() or "parse" in str(e).lower():
                    if attempt < self.max_retries:
                        delay = self.retry_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        self.stats.inc(retries=1)
                        time.sleep(delay)
                    else:
                        # 达到最大重试
                        self.stats.inc(failed_chunks=1)
                        raise ExtractionError(
                            f"Max retries ({self.max_retries}) exceeded. Last error: {e}",
                            error_type="max_retries",
                        )
                else:
                    # 不确定的错误类型，不重试
                    raise ExtractionError(
                        f"Unknown error (not retrying): {e}",
                        error_type="unknown_non_retryable",
                    )

        # 不应到达这里
        raise ExtractionError(
            f"Extraction failed: {last_error}",
            error_type="unknown",
        )

    def _call_llm(
        self,
        user_prompt: str,
        *,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> tuple[str, list[Triple]]:
        """调用 LLM API."""
        kwargs: dict = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        if self.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content or ""

        if response.usage:
            self.stats.inc(
                total_tokens=response.usage.total_tokens,
                total_input_tokens=response.usage.prompt_tokens or 0,
                total_output_tokens=response.usage.completion_tokens or 0,
            )

        triples = self._parse_response(raw)
        return raw, triples

    def _parse_response(self, raw: str) -> list[Triple]:
        """从 LLM 原始响应中解析三元组列表.

        兼容格式:
        1. 纯 JSON 数组 [{...}, ...]
        2. JSON object: {"triples": [...]}
        3. 批量格式: {"results": [{"chunk_id": ..., "triples": [...]}, ...]}
        4. Markdown 代码块包裹
        """
        text = raw.strip()

        # 尝试 1: 直接 JSON 解析
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [Triple(**item) for item in data]
            if isinstance(data, dict):
                # 先检查批量格式 {"results": [{chunk_id, triples}, ...]}
                if "results" in data:
                    all_t = []
                    for entry in data["results"]:
                        if isinstance(entry, dict) and "triples" in entry:
                            for t in entry["triples"]:
                                if isinstance(t, dict):
                                    all_t.append(Triple(**t))
                    if all_t:
                        return all_t
                    if isinstance(data["results"], list):
                        items = data["results"]
                else:
                    items = data.get("triples", data.get("results", []))
                if isinstance(items, list):
                    return [Triple(**item) for item in items if isinstance(item, dict)]
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试 2: markdown 代码块
        code_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(code_pattern, text, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, list):
                    return [Triple(**item) for item in data]
                if isinstance(data, dict):
                    if "results" in data:
                        all_t = []
                        for entry in data["results"]:
                            for t in entry.get("triples", []):
                                if isinstance(t, dict):
                                    all_t.append(Triple(**t))
                        if all_t:
                            return all_t
                    items = data.get("triples", [])
                    return [Triple(**item) for item in items]
            except (json.JSONDecodeError, TypeError):
                continue

        # 尝试 3: 提取最外层 JSON 数组
        array_pattern = r"\[\s*\{.*?\}\s*\]"
        match = re.search(array_pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return [Triple(**item) for item in data]
            except (json.JSONDecodeError, TypeError):
                pass

        # 保存原始响应用于调试
        debug_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "failed_responses"
        )
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = os.path.join(debug_dir, f"failed_{hashlib.md5(raw.encode()).hexdigest()[:8]}.txt")
        try:
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(raw)
        except OSError:
            pass

        raise ValueError(
            f"Unable to parse LLM response as JSON triples. "
            f"Raw response saved to {debug_file}. "
            f"First 200 chars: {text[:200]}"
        )

    # ------------------------------------------------------------------
    # 三元组验证
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_paper_relations(
        triples: list[Triple], paper_id: str
    ) -> list[Triple]:
        """把论文级关系规范化为 ``Paper -> 研究对象``。

        旧 Prompt 会把论文级关系错误地输出成自循环。这里保留实际对象，
        用调用方提供的 paper_id 作为 head，确保图谱中出现可追溯的论文节点。
        """
        if not paper_id:
            return triples

        for triple in triples:
            if triple.relation not in PAPER_RELATIONS:
                continue

            # 旧格式通常是 head == tail；此时实体本身就是论文关系的对象。
            if triple.head.strip().lower() == triple.tail.strip().lower():
                target_name = triple.head
                target_type = triple.head_type
            else:
                target_name = triple.tail
                target_type = triple.tail_type

            triple.head = paper_id
            triple.head_type = EntityType.PAPER.value
            triple.tail = target_name
            triple.tail_type = target_type

        return triples

    @staticmethod
    def _validate_triple(triple: Triple) -> bool:
        """验证三元组是否合法."""
        head = triple.head.strip()
        tail = triple.tail.strip()
        if not head or not tail:
            return False
        if head.casefold() == tail.casefold():
            return False
        if len(head) > MAX_ENTITY_CHARS or len(tail) > MAX_ENTITY_CHARS:
            return False
        if len(head.split()) > MAX_ENTITY_WORDS or len(tail.split()) > MAX_ENTITY_WORDS:
            return False
        # 完整句子应进入 evidence/Claim，而不是充当实体名称。
        sentence_markers = re.compile(
            r"\b(significantly|influences?|improves?|affects?|predicts?|"
            r"moderates?|showed|shows|indicates?|does not|were|was)\b",
            re.IGNORECASE,
        )
        if (
            re.search(r"[.!?](?:\s+|$)", head)
            or re.search(r"[.!?](?:\s+|$)", tail)
            or (len(head.split()) >= 6 and sentence_markers.search(head))
            or (len(tail.split()) >= 6 and sentence_markers.search(tail))
        ):
            return False

        valid_entities = {e.value for e in EntityType}
        if triple.head_type not in valid_entities:
            return False
        if triple.tail_type not in valid_entities:
            return False
        valid_relations = {r.value for r in RelationType}
        if triple.relation not in valid_relations:
            return False
        relation_enum = RelationType(triple.relation)
        allowed_heads = RELATION_HEAD_CONSTRAINTS.get(relation_enum)
        if allowed_heads and triple.head_type not in {t.value for t in allowed_heads}:
            return False
        if not triple.evidence.strip():
            return False
        if not (0.0 <= triple.confidence <= 1.0):
            return False
        return True

    # ------------------------------------------------------------------
    # 去重 & 合并
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate_local(triples: list[Triple]) -> list[Triple]:
        """本地去重: 按 (norm_head, relation, norm_tail) 去重.

        合并规则:
          - 合并 evidence（保留完整原文）
          - 合并 source_chunk_id 和 source_chunk_ids（去重 + 稳定排序）
          - 合并 source_chunk_index 和 source_chunk_indices（去重 + 稳定排序）
          - 保留最高 confidence
          - 保留 layer（L3 优先）
          - 保留 new_type_suggestion
          - 结果顺序稳定（第一次出现的 key 确定位置）
        """
        seen: dict[tuple[str, str, str], Triple] = {}
        order: list[tuple[str, str, str]] = []

        for t in triples:
            key = (t.head.lower().strip(), t.relation, t.tail.lower().strip())
            if key in seen:
                existing = seen[key]
                # 合并 evidence
                if t.evidence not in existing.evidence:
                    existing.evidence = existing.evidence + " | " + t.evidence
                # 保留最高 confidence
                if t.confidence > existing.confidence:
                    existing.confidence = t.confidence
                # 合并 chunk 来源（去重）
                if t.source_chunk_id and t.source_chunk_id not in existing.source_chunk_ids:
                    existing.source_chunk_ids.append(t.source_chunk_id)
                if t.source_chunk_index >= 0 and t.source_chunk_index not in existing.source_chunk_indices:
                    existing.source_chunk_indices.append(t.source_chunk_index)
                # 保留单值字段为第一个来源
                if not existing.source_chunk_id and t.source_chunk_id:
                    existing.source_chunk_id = t.source_chunk_id
                if existing.source_chunk_index < 0 and t.source_chunk_index >= 0:
                    existing.source_chunk_index = t.source_chunk_index
                # 保留 non-None new_type_suggestion
                if t.new_type_suggestion and not existing.new_type_suggestion:
                    existing.new_type_suggestion = t.new_type_suggestion
                # 保留 layer (L3 优先)
                if t.layer == "L3" and existing.layer != "L3":
                    existing.layer = t.layer
                # 稳定排序来源列表
                existing.source_chunk_ids = sorted(set(existing.source_chunk_ids))
                existing.source_chunk_indices = sorted(set(existing.source_chunk_indices))
            else:
                # 初始化来源列表（去重 + 排序）
                init_ids = list(t.source_chunk_ids) if t.source_chunk_ids else (
                    [t.source_chunk_id] if t.source_chunk_id else []
                )
                init_indices = list(t.source_chunk_indices) if t.source_chunk_indices else (
                    [t.source_chunk_index] if t.source_chunk_index >= 0 else []
                )
                new_t = Triple(
                    head=t.head, head_type=t.head_type,
                    relation=t.relation, tail=t.tail, tail_type=t.tail_type,
                    evidence=t.evidence, confidence=t.confidence,
                    new_type_suggestion=t.new_type_suggestion, layer=t.layer,
                    source_chunk_id=t.source_chunk_id,
                    source_chunk_index=t.source_chunk_index,
                    source_chunk_ids=sorted(set(init_ids)),
                    source_chunk_indices=sorted(set(init_indices)),
                )
                seen[key] = new_t
                order.append(key)

        return [seen[k] for k in order]

    def _merge_triples_llm(self, triples: list[Triple]) -> list[Triple]:
        """通过 LLM 合并去重 (仅在 merge_mode='llm' 时调用).

        LLM 合并失败时回退到本地去重，不丢失结果。
        """
        if len(triples) < 20:
            return self._deduplicate_local(triples)

        triples_json = json.dumps(
            [t.model_dump() for t in triples], ensure_ascii=False, indent=2
        )
        merge_prompt = build_merge_prompt(triples_json)

        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": merge_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            if response.usage:
                self.stats.inc(
                    total_tokens=response.usage.total_tokens,
                    total_input_tokens=response.usage.prompt_tokens or 0,
                    total_output_tokens=response.usage.completion_tokens or 0,
                )
            merged = self._parse_response(raw)
            if not merged:
                return self._deduplicate_local(triples)
            return merged
        except Exception:
            # LLM 合并失败 → 回退到本地去重，不丢失结果
            return self._deduplicate_local(triples)

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        try:
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": "Reply with just: OK"}],
                max_tokens=10,
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            return "OK" in content
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def get_stats(self) -> ExtractionStats:
        s = self.stats
        s.cost_yuan = estimate_cost_yuan(
            self.preset_name, s.total_input_tokens, s.total_output_tokens
        )
        if self._cache:
            cs = self._cache.get_stats()
            s.cache_hits = cs.hits + cs.batch_hits
            s.cache_misses = cs.misses + cs.batch_misses
        return s

    def budget_exceeded(self) -> bool:
        if self.budget_yuan <= 0:
            return False
        self.get_stats()
        return self.stats.cost_yuan >= self.budget_yuan

    def budget_remaining_str(self) -> str:
        if self.budget_yuan <= 0:
            return "unlimited"
        self.get_stats()
        return (f"{self.stats.cost_yuan:.2f}/{self.budget_yuan:.2f} yuan "
                f"({self.budget_yuan - self.stats.cost_yuan:.2f} left)")

    def reset_stats(self) -> None:
        self.stats = ExtractionStats()

    def clear_cache(self, paper_id: str = "") -> int:
        if self._cache:
            return self._cache.clear(paper_id=paper_id)
        return 0

    @classmethod
    def list_presets(cls) -> list[dict]:
        return [
            {"key": k, "name": p.name, "description": p.description, "model_id": p.model_id}
            for k, p in PRESETS.items()
        ]
