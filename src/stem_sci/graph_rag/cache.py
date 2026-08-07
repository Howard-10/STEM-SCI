"""SQLite 抽取结果缓存层.

双层缓存:
  单 chunk 缓存键: paper_id + chunk_sha256 + model_id + prompt_version + schema_version
  批量缓存键: paper_id + ordered_chunk_sha256s + model_id + batch_size + batch_prompt_version + schema_version

缓存内容: raw_response + parsed_triples + metadata
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schema import BATCH_PROMPT_VERSION, PROMPT_VERSION, SCHEMA_VERSION
from .schema import ChunkTriples, Triple


def _default_cache_dir() -> str:
    """默认缓存目录，通过环境变量配置."""
    env_dir = os.getenv("STEM_KB_CACHE_DIR", "")
    if env_dir:
        return env_dir
    return str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "extraction_cache")


@dataclass
class CacheStats:
    """缓存统计."""
    hits: int = 0
    misses: int = 0
    writes: int = 0
    errors: int = 0
    batch_hits: int = 0
    batch_misses: int = 0
    batch_writes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def batch_hit_rate(self) -> float:
        total = self.batch_hits + self.batch_misses
        return self.batch_hits / total if total > 0 else 0.0


class ExtractionCache:
    """SQLite 抽取缓存 —— 支持单 chunk 与批量缓存.

    使用方式:
        cache = ExtractionCache()

        # 单 chunk
        entry = cache.get(cache_key)
        cache.put(cache_key, raw_response, triples, ...)

        # 批量
        batch_entry = cache.get_batch(batch_key)
        cache.put_batch(batch_key, raw_response, chunk_results, ...)
    """

    def __init__(self, db_path: str = "") -> None:
        self.db_path = db_path or os.path.join(_default_cache_dir(), "cache.db")
        self.stats = CacheStats()
        self._lock = threading.Lock()
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            # 单 chunk 缓存表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extraction_cache (
                    cache_key TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    chunk_index INTEGER DEFAULT 0,
                    chunk_sha256 TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    triples_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    retry_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_paper
                ON extraction_cache(paper_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_model
                ON extraction_cache(model_id, prompt_version, schema_version)
            """)

            # 批量缓存表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_extraction_cache (
                    batch_cache_key TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    chunk_sha256s_json TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    batch_size INTEGER NOT NULL,
                    batch_prompt_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    chunk_results_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    retry_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_batch_cache_paper
                ON batch_extraction_cache(paper_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_batch_cache_model
                ON batch_extraction_cache(model_id, batch_prompt_version, schema_version)
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # 缓存键构造
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(
        paper_id: str,
        chunk_sha256: str,
        model_id: str,
        prompt_version: str = "",
        schema_version: str = "",
    ) -> str:
        """构造单 chunk 缓存键."""
        pv = prompt_version or PROMPT_VERSION
        sv = schema_version or SCHEMA_VERSION
        raw = f"{paper_id}|{chunk_sha256}|{model_id}|{pv}|{sv}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def make_batch_key(
        paper_id: str,
        ordered_chunk_sha256s: list[str],
        model_id: str,
        batch_size: int,
        batch_prompt_version: str = "",
        schema_version: str = "",
    ) -> str:
        """构造批量缓存键.

        缓存键依赖:
          - paper_id
          - 有序 chunk SHA256 列表 (保证不同邻居组合不共用缓存)
          - model_id
          - batch_size (不同 batch_size 不共用缓存)
          - batch_prompt_version (prompt 版本变更后自动失效)
          - schema_version (schema 版本变更后自动失效)
        """
        bpv = batch_prompt_version or BATCH_PROMPT_VERSION
        sv = schema_version or SCHEMA_VERSION
        chunks_joined = ",".join(ordered_chunk_sha256s)
        raw = f"{paper_id}|{chunks_joined}|{model_id}|{batch_size}|{bpv}|{sv}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------
    # 单 chunk 读/写
    # ------------------------------------------------------------------

    def get(
        self,
        cache_key: str,
    ) -> Optional[dict]:
        """读取缓存条目.

        Returns:
            {"triples": [...], "raw_response": "..."} or None
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT triples_json, raw_response FROM extraction_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
                if row:
                    with self._lock:
                        self.stats.hits += 1
                    return {
                        "triples": [Triple(**t) for t in json.loads(row["triples_json"])],
                        "raw_response": row["raw_response"],
                    }
                else:
                    with self._lock:
                        self.stats.misses += 1
                    return None
        except Exception:
            with self._lock:
                self.stats.errors += 1
            return None

    def put(
        self,
        cache_key: str,
        raw_response: str,
        triples: list[Triple],
        paper_id: str = "",
        chunk_index: int = 0,
        chunk_sha256: str = "",
        model_id: str = "",
        prompt_version: str = "",
        schema_version: str = "",
        retry_count: int = 0,
    ) -> None:
        """写入单 chunk 缓存."""
        triples_json = json.dumps(
            [t.model_dump() for t in triples], ensure_ascii=False
        )
        pv = prompt_version or PROMPT_VERSION
        sv = schema_version or SCHEMA_VERSION
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO extraction_cache
                        (cache_key, paper_id, chunk_index, chunk_sha256,
                         model_id, prompt_version, schema_version,
                         raw_response, triples_json, retry_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cache_key, paper_id, chunk_index, chunk_sha256,
                        model_id, pv, sv,
                        raw_response, triples_json, retry_count,
                    ),
                )
                conn.commit()
            with self._lock:
                self.stats.writes += 1
        except Exception:
            with self._lock:
                self.stats.errors += 1

    # ------------------------------------------------------------------
    # 单 chunk 批量读 (多 key 一次查询)
    # ------------------------------------------------------------------

    def get_multi(
        self,
        cache_keys: list[str],
    ) -> dict[str, Optional[dict]]:
        """批量读取单 chunk 缓存条目.

        Returns:
            {cache_key: {"triples": [...], "raw_response": "..."} or None}
        """
        result: dict[str, Optional[dict]] = {}
        if not cache_keys:
            return result
        try:
            with self._connect() as conn:
                placeholders = ",".join("?" * len(cache_keys))
                rows = conn.execute(
                    f"SELECT cache_key, triples_json, raw_response FROM extraction_cache WHERE cache_key IN ({placeholders})",
                    cache_keys,
                ).fetchall()
                found = {r["cache_key"]: r for r in rows}

            for key in cache_keys:
                if key in found:
                    r = found[key]
                    result[key] = {
                        "triples": [Triple(**t) for t in json.loads(r["triples_json"])],
                        "raw_response": r["raw_response"],
                    }
                    with self._lock:
                        self.stats.hits += 1
                else:
                    result[key] = None
                    with self._lock:
                        self.stats.misses += 1
        except Exception:
            with self._lock:
                self.stats.errors += 1
            for key in cache_keys:
                result[key] = None

        return result

    # ------------------------------------------------------------------
    # 批量缓存读/写
    # ------------------------------------------------------------------

    def get_batch(
        self,
        batch_cache_key: str,
    ) -> Optional[dict]:
        """读取批量缓存条目.

        Returns:
            {
                "chunk_results": [ChunkTriples, ...],
                "raw_response": "...",
                "retry_count": 0
            } or None
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT chunk_results_json, raw_response, retry_count "
                    "FROM batch_extraction_cache WHERE batch_cache_key = ?",
                    (batch_cache_key,),
                ).fetchone()
                if row:
                    with self._lock:
                        self.stats.batch_hits += 1
                    chunk_data = json.loads(row["chunk_results_json"])
                    chunk_results = [
                        ChunkTriples(
                            chunk_id=cd["chunk_id"],
                            chunk_index=cd["chunk_index"],
                            triples=[Triple(**t) for t in cd["triples"]],
                            status=cd.get("status", "success"),
                            error_message=cd.get("error_message", ""),
                        )
                        for cd in chunk_data
                    ]
                    return {
                        "chunk_results": chunk_results,
                        "raw_response": row["raw_response"],
                        "retry_count": row["retry_count"],
                    }
                else:
                    with self._lock:
                        self.stats.batch_misses += 1
                    return None
        except Exception:
            with self._lock:
                self.stats.errors += 1
            return None

    def get_batch_multi(
        self,
        batch_cache_keys: list[str],
    ) -> dict[str, Optional[dict]]:
        """批量读取多个批量缓存条目.

        Returns:
            {batch_cache_key: {...} or None}
        """
        result: dict[str, Optional[dict]] = {}
        if not batch_cache_keys:
            return result
        try:
            with self._connect() as conn:
                placeholders = ",".join("?" * len(batch_cache_keys))
                rows = conn.execute(
                    f"SELECT batch_cache_key, chunk_results_json, raw_response, retry_count "
                    f"FROM batch_extraction_cache WHERE batch_cache_key IN ({placeholders})",
                    batch_cache_keys,
                ).fetchall()
                found = {r["batch_cache_key"]: r for r in rows}

            for key in batch_cache_keys:
                if key in found:
                    r = found[key]
                    chunk_data = json.loads(r["chunk_results_json"])
                    chunk_results = [
                        ChunkTriples(
                            chunk_id=cd["chunk_id"],
                            chunk_index=cd["chunk_index"],
                            triples=[Triple(**t) for t in cd["triples"]],
                            status=cd.get("status", "success"),
                            error_message=cd.get("error_message", ""),
                        )
                        for cd in chunk_data
                    ]
                    result[key] = {
                        "chunk_results": chunk_results,
                        "raw_response": r["raw_response"],
                        "retry_count": r["retry_count"],
                    }
                    with self._lock:
                        self.stats.batch_hits += 1
                else:
                    result[key] = None
                    with self._lock:
                        self.stats.batch_misses += 1
        except Exception:
            with self._lock:
                self.stats.errors += 1
            for key in batch_cache_keys:
                result[key] = None

        return result

    def put_batch(
        self,
        batch_cache_key: str,
        raw_response: str,
        chunk_results: list[ChunkTriples],
        paper_id: str = "",
        chunk_sha256s: Optional[list[str]] = None,
        model_id: str = "",
        batch_size: int = 0,
        batch_prompt_version: str = "",
        schema_version: str = "",
        retry_count: int = 0,
    ) -> None:
        """写入批量缓存.

        保存完整 batch 原始响应和每个 chunk 的解析结果。
        缓存命中后仍然保留 chunk 来源。
        """
        chunk_results_json = json.dumps(
            [
                {
                    "chunk_id": cr.chunk_id,
                    "chunk_index": cr.chunk_index,
                    "triples": [t.model_dump() for t in cr.triples],
                    "status": cr.status,
                    "error_message": cr.error_message,
                }
                for cr in chunk_results
            ],
            ensure_ascii=False,
        )
        chunk_sha256s_json = json.dumps(chunk_sha256s or [], ensure_ascii=False)
        bpv = batch_prompt_version or BATCH_PROMPT_VERSION
        sv = schema_version or SCHEMA_VERSION

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO batch_extraction_cache
                        (batch_cache_key, paper_id, chunk_sha256s_json,
                         model_id, batch_size, batch_prompt_version, schema_version,
                         raw_response, chunk_results_json, retry_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_cache_key, paper_id, chunk_sha256s_json,
                        model_id, batch_size, bpv, sv,
                        raw_response, chunk_results_json, retry_count,
                    ),
                )
                conn.commit()
            with self._lock:
                self.stats.batch_writes += 1
        except Exception:
            with self._lock:
                self.stats.errors += 1

    # ------------------------------------------------------------------
    # 批量预读（一次性读取所有 batch keys，避免逐个打开连接）
    # ------------------------------------------------------------------

    def preload_batch_cache(
        self,
        batch_keys: list[str],
    ) -> dict[str, Optional[dict]]:
        """一次性读取所有 batch 缓存键.

        Args:
            batch_keys: 批量缓存键列表

        Returns:
            {batch_cache_key: cached_data or None}
        """
        return self.get_batch_multi(batch_keys)

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    def clear(self, paper_id: str = "", model_id: str = "") -> int:
        """清除缓存 (同时清除单 chunk 和批量缓存).

        Args:
            paper_id: 指定论文 (空=全部)
            model_id: 指定模型 (空=全部)

        Returns:
            删除的条目数
        """
        conditions = []
        params: list = []
        if paper_id:
            conditions.append("paper_id = ?")
            params.append(paper_id)
        if model_id:
            conditions.append("model_id = ?")
            params.append(model_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        total = 0
        with self._connect() as conn:
            cursor = conn.execute(f"DELETE FROM extraction_cache WHERE {where}", params)
            total += cursor.rowcount
            cursor2 = conn.execute(f"DELETE FROM batch_extraction_cache WHERE {where}", params)
            total += cursor2.rowcount
            conn.commit()
        return total

    def invalidate_by_version(
        self,
        old_prompt_version: str = "",
        old_schema_version: str = "",
        old_batch_prompt_version: str = "",
    ) -> int:
        """按版本失效缓存."""
        total = 0
        with self._connect() as conn:
            # 单 chunk 缓存
            sc_conditions = []
            sc_params = []
            if old_prompt_version:
                sc_conditions.append("prompt_version != ?")
                sc_params.append(old_prompt_version)
            if old_schema_version:
                sc_conditions.append("schema_version != ?")
                sc_params.append(old_schema_version)
            if sc_conditions:
                where = " AND ".join(sc_conditions)
                cursor = conn.execute(f"DELETE FROM extraction_cache WHERE {where}", sc_params)
                total += cursor.rowcount

            # 批量缓存
            bc_conditions = []
            bc_params = []
            if old_batch_prompt_version:
                bc_conditions.append("batch_prompt_version != ?")
                bc_params.append(old_batch_prompt_version)
            if old_schema_version:
                bc_conditions.append("schema_version != ?")
                bc_params.append(old_schema_version)
            if bc_conditions:
                where = " AND ".join(bc_conditions)
                cursor2 = conn.execute(f"DELETE FROM batch_extraction_cache WHERE {where}", bc_params)
                total += cursor2.rowcount

            conn.commit()
        return total

    def get_stats(self) -> CacheStats:
        return self.stats

    def count(self) -> int:
        with self._connect() as conn:
            r1 = conn.execute("SELECT COUNT(*) FROM extraction_cache").fetchone()[0]
            r2 = conn.execute("SELECT COUNT(*) FROM batch_extraction_cache").fetchone()[0]
            return r1 + r2

    def count_batch(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM batch_extraction_cache").fetchone()[0]
