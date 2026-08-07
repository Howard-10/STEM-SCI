"""自举式 Schema 注册表 —— 让知识图谱的类型系统随文献增长自我演化.

机制:
  1. LLM 抽取时遇到无法归类的概念 → 标记为 Concept / RELATED_TO
     并在 new_type_suggestion 字段建议新类型名
  2. record_suggestion() 记录每个建议，累计频次
  3. 当某个建议超过阈值（默认出现 ≥ 5 次），generate_promotion_candidates() 返回待升级列表
  4. 人工确认后调用 promote_type() → 新类型加入 EntityType/RelationType 动态注册表

存储: SQLite（零额外依赖，与项目已有 MVP 一致）
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class SuggestionRecord:
    """一条类型建议记录."""

    suggestion_name: str
    category: str  # "entity" | "relation"
    source_paper: str
    count: int = 1
    examples: list[str] = field(default_factory=list)  # 样例实体名


@dataclass
class PromotionCandidate:
    """待人工确认的升级候选."""

    suggestion_name: str
    category: str  # "entity" | "relation"
    total_occurrences: int
    source_papers: list[str]
    example_entities: list[str]
    recommended_display_name: str


# ============================================================================
# SchemaRegistry
# ============================================================================


class SchemaRegistry:
    """自举式类型注册表.

    使用方式:
        registry = SchemaRegistry("path/to/schema_registry.db")
        registry.record_suggestion("citizen-science", "entity", "paper_001", ["citizen science"])
        candidates = registry.generate_promotion_candidates(min_occurrences=5)
        registry.promote("citizen-science", "entity", "CitizenScience")
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            # 默认路径: 项目根目录下的 data 文件夹
            db_path = str(
                Path(__file__).resolve().parent.parent.parent.parent
                / "data"
                / "schema_registry.db"
            )
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保数据库表存在."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS type_suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    suggestion_name TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('entity', 'relation')),
                    source_paper TEXT NOT NULL,
                    example_value TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(suggestion_name, category, source_paper)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS promoted_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    internal_name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('entity', 'relation')),
                    promoted_at TEXT DEFAULT (datetime('now')),
                    is_active INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical TEXT NOT NULL,
                    alias TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ------------------------------------------------------------------
    # 记录建议
    # ------------------------------------------------------------------

    def record_suggestion(
        self,
        suggestion_name: str,
        category: str,
        source_paper: str,
        examples: Optional[list[str]] = None,
    ) -> None:
        """记录一条新类型建议.

        Args:
            suggestion_name: LLM 建议的类型名 (kebab-case)
            category: "entity" 或 "relation"
            source_paper: 来源论文 ID
            examples: 触发此建议的实体示例
        """
        name = suggestion_name.strip().lower().replace(" ", "-")
        example_str = json.dumps(examples or [], ensure_ascii=False)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO type_suggestions
                    (suggestion_name, category, source_paper, example_value)
                VALUES (?, ?, ?, ?)
                """,
                (name, category, source_paper, example_str),
            )
            conn.commit()

    def record_from_triple(self, triple, paper_id: str) -> None:
        """从含有 new_type_suggestion 的 Triple 自动记录."""
        suggestion = triple.new_type_suggestion
        if not suggestion:
            return

        # 实体类型建议
        if triple.head_type == "Concept":
            self.record_suggestion(suggestion, "entity", paper_id, [triple.head])
        else:
            self.record_suggestion(suggestion, "entity", paper_id, [triple.head])

        if triple.tail_type == "Concept":
            self.record_suggestion(suggestion, "entity", paper_id, [triple.tail])

        # 关系类型建议
        if triple.relation == "RELATED_TO":
            self.record_suggestion(suggestion, "relation", paper_id, [triple.relation])

    def record_batch_from_triples(
        self,
        triples: list,
        paper_id: str,
    ) -> int:
        """批量从 Triple 列表记录建议.

        Returns:
            记录的建议数
        """
        count = 0
        for t in triples:
            if t.new_type_suggestion:
                self.record_from_triple(t, paper_id)
                count += 1
        return count

    # ------------------------------------------------------------------
    # 统计与查询
    # ------------------------------------------------------------------

    def get_suggestion_stats(self) -> dict:
        """获取建议统计."""
        with self._connect() as conn:
            # 按建议名聚合
            rows = conn.execute("""
                SELECT
                    suggestion_name,
                    category,
                    COUNT(DISTINCT source_paper) AS paper_count,
                    COUNT(*) AS total_records
                FROM type_suggestions
                GROUP BY suggestion_name, category
                ORDER BY paper_count DESC, total_records DESC
            """).fetchall()

            entity_suggestions = []
            relation_suggestions = []
            for r in rows:
                item = {
                    "name": r["suggestion_name"],
                    "paper_count": r["paper_count"],
                    "total_records": r["total_records"],
                }
                if r["category"] == "entity":
                    entity_suggestions.append(item)
                else:
                    relation_suggestions.append(item)

            total = conn.execute(
                "SELECT COUNT(DISTINCT suggestion_name) FROM type_suggestions"
            ).fetchone()[0]

            return {
                "total_unique_suggestions": total,
                "entity_suggestions": entity_suggestions,
                "relation_suggestions": relation_suggestions,
            }

    def generate_promotion_candidates(
        self,
        min_occurrences: int = 5,
    ) -> list[PromotionCandidate]:
        """生成待升级的类型候选列表.

        Args:
            min_occurrences: 最少在不同论文中出现次数

        Returns:
            按频次降序排列的候选列表
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT
                    suggestion_name,
                    category,
                    COUNT(DISTINCT source_paper) AS paper_count,
                    GROUP_CONCAT(DISTINCT source_paper) AS papers,
                    GROUP_CONCAT(DISTINCT example_value) AS examples
                FROM type_suggestions
                GROUP BY suggestion_name, category
                HAVING paper_count >= ?
                ORDER BY paper_count DESC
            """, (min_occurrences,)).fetchall()

            candidates = []
            for r in rows:
                # 解析示例
                examples = []
                raw_examples = r["examples"] or ""
                for part in raw_examples.split(","):
                    try:
                        parsed = json.loads(part)
                        if isinstance(parsed, list):
                            examples.extend(parsed)
                        else:
                            examples.append(str(parsed))
                    except json.JSONDecodeError:
                        if part.strip():
                            examples.append(part.strip())

                # 去重
                examples = list(dict.fromkeys(examples))[:10]

                # 生成推荐显示名
                display = r["suggestion_name"].replace("-", " ").title().replace(" ", "")

                candidates.append(
                    PromotionCandidate(
                        suggestion_name=r["suggestion_name"],
                        category=r["category"],
                        total_occurrences=r["paper_count"],
                        source_papers=r["papers"].split(",") if r["papers"] else [],
                        example_entities=examples,
                        recommended_display_name=display,
                    )
                )

        return candidates

    # ------------------------------------------------------------------
    # 类型升级
    # ------------------------------------------------------------------

    def promote(self, internal_name: str, category: str, display_name: str = "") -> None:
        """将建议类型升级为正式类型.

        Args:
            internal_name: 建议的内部名 (kebab-case)
            category: "entity" 或 "relation"
            display_name: 显示名 (PascalCase)，默认从 internal_name 生成
        """
        if not display_name:
            display_name = internal_name.replace("-", " ").title().replace(" ", "")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO promoted_types
                    (internal_name, display_name, category, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (internal_name, display_name, category),
            )
            conn.commit()

    def get_promoted_types(self, category: Optional[str] = None) -> list[dict]:
        """获取所有已升级的类型."""
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    """
                    SELECT * FROM promoted_types
                    WHERE category = ? AND is_active = 1
                    ORDER BY promoted_at DESC
                    """,
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM promoted_types
                    WHERE is_active = 1
                    ORDER BY category, promoted_at DESC
                    """,
                ).fetchall()
        return [dict(r) for r in rows]

    def deactivate(self, internal_name: str) -> None:
        """停用某个已升级类型（软删除）."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE promoted_types SET is_active = 0 WHERE internal_name = ?",
                (internal_name,),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # 实体别名管理（归一化）
    # ------------------------------------------------------------------

    def add_alias(self, canonical: str, alias: str, entity_type: str) -> None:
        """注册实体别名，用于归一化."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO entity_aliases (canonical, alias, entity_type)
                VALUES (?, ?, ?)
                """,
                (canonical.strip().lower(), alias.strip().lower(), entity_type),
            )
            conn.commit()

    def resolve_alias(self, name: str) -> Optional[str]:
        """查找名称的规范形式."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT canonical FROM entity_aliases WHERE alias = ?",
                (name.strip().lower(),),
            ).fetchone()
            return row["canonical"] if row else None

    def add_alias_batch(self, pairs: list[tuple[str, str, str]]) -> int:
        """批量添加别名 [(canonical, alias, entity_type), ...].

        Returns:
            添加的别名数
        """
        count = 0
        with self._connect() as conn:
            for canonical, alias, entity_type in pairs:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO entity_aliases (canonical, alias, entity_type)
                    VALUES (?, ?, ?)
                    """,
                    (canonical.strip().lower(), alias.strip().lower(), entity_type),
                )
                count += 1
            conn.commit()
        return count
