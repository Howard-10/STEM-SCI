"""Neo4j 知识图谱存储 —— 按 project_id 隔离的 CRUD 操作.

使用方式:
    store = GraphStore.from_env()
    store.upsert_paper(paper_meta)
    store.upsert_triple(triple, project_id, paper_id)
    results = store.query_evidence("thermodynamics", project_id)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

from .schema import Triple


# ============================================================================
# 配置
# ============================================================================


@dataclass
class Neo4jConfig:
    """Neo4j 连接配置."""

    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "neo4j"
    database: str = "neo4j"


def _env_neo4j(key: str, default: str = "") -> str:
    return os.getenv(f"NEO4J_{key}", default)


# ============================================================================
# GraphStore
# ============================================================================


class GraphStore:
    """Neo4j 知识图谱存储.

    所有节点和关系自动携带 project_id 属性以实现多项目隔离。
    """

    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self._driver: Optional[Driver] = None

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, **overrides) -> "GraphStore":
        """从环境变量创建连接."""
        cfg = Neo4jConfig(
            uri=overrides.pop("uri", _env_neo4j("URI", "bolt://localhost:7687")),
            username=overrides.pop("username", _env_neo4j("USERNAME", "neo4j")),
            password=overrides.pop("password", _env_neo4j("PASSWORD", "neo4j")),
            database=overrides.pop("database", _env_neo4j("DATABASE", "neo4j")),
        )
        return cls(cfg)

    @classmethod
    def from_config(cls, uri: str, username: str, password: str, **kwargs) -> "GraphStore":
        """显式传参创建连接."""
        cfg = Neo4jConfig(uri=uri, username=username, password=password, **kwargs)
        return cls(cfg)

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
            )
            self._driver.verify_connectivity()
        return self._driver

    def session(self) -> Session:
        return self.driver.session(database=self.config.database)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def health_check(self) -> bool:
        """测试 Neo4j 连通性."""
        try:
            self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, AuthError, OSError) as e:
            print(f"Neo4j health check failed: {e}")
            return False

    # ------------------------------------------------------------------
    # 索引创建（首次初始化时调用）
    # ------------------------------------------------------------------

    def ensure_indexes(self) -> None:
        """确保必要索引存在.

        包含:
          - Entity: (project_id, entity_type, name) 复合索引
          - Paper: (doi, project_id) 复合索引（支持 project_id 隔离）
          - RELATES 关系: project_id 索引
        """
        indexes = [
            # 实体节点: 按 (project_id, entity_type, name) 快速查找
            "CREATE INDEX entity_lookup IF NOT EXISTS "
            "FOR (n:Entity) ON (n.project_id, n.entity_type, n.name)",
            # 论文节点: 按 (doi, project_id) 快速查找 + 唯一约束
            "CREATE INDEX paper_doi_project IF NOT EXISTS "
            "FOR (p:Paper) ON (p.doi, p.project_id)",
        ]

        # 如果 Neo4j 版本支持 unique constraint，添加 (doi, project_id) 唯一约束
        try:
            with self.session() as sess:
                sess.run(
                    "CREATE CONSTRAINT paper_doi_project_unique IF NOT EXISTS "
                    "FOR (p:Paper) REQUIRE (p.doi, p.project_id) IS UNIQUE"
                )
        except Exception:
            # 旧版 Neo4j 不支持约束语法，回退到仅索引
            pass

        with self.session() as sess:
            for stmt in indexes:
                try:
                    sess.run(stmt)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Paper 节点
    # ------------------------------------------------------------------

    def upsert_paper(
        self,
        doi: str,
        *,
        title: str = "",
        year: int = 0,
        journal: str = "",
        project_id: str = "default",
        **extra_props,
    ) -> None:
        """创建或更新论文节点.

        唯一键: (doi, project_id)
        """
        cypher = """
        MERGE (p:Paper {doi: $doi, project_id: $project_id})
        SET p.title = $title,
            p.year = $year,
            p.journal = $journal,
            p.name = $doi,
            p.entity_type = 'Paper',
            p.updated_at = datetime()
        """
        params = {
            "doi": doi,
            "project_id": project_id,
            "title": title,
            "year": year,
            "journal": journal,
        }
        params.update(extra_props)

        with self.session() as sess:
            sess.run(cypher, params)

    def upsert_papers_batch(
        self,
        papers: list[dict],
        *,
        project_id: str = "default",
    ) -> int:
        """批量导入论文节点.

        使用 (doi, project_id) 作为唯一键，防止不同项目互相覆盖。

        Args:
            papers: [{"doi": ..., "title": ..., "year": ..., "journal": ...}, ...]
            project_id: 项目 ID

        Returns:
            导入的论文数
        """
        cypher = """
        UNWIND $papers AS paper
        MERGE (p:Paper {doi: paper.doi, project_id: $project_id})
        SET p.title = paper.title,
            p.year = paper.year,
            p.journal = paper.journal,
            p.authors = paper.authors,
            p.name = paper.doi,
            p.entity_type = 'Paper',
            p.updated_at = datetime()
        RETURN count(p) AS cnt
        """
        with self.session() as sess:
            result = sess.run(cypher, {"papers": papers, "project_id": project_id})
            record = result.single()
            return record["cnt"] if record else 0

    # ------------------------------------------------------------------
    # Entity 节点 (L2 研究要素)
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        name: str,
        entity_type: str,
        *,
        project_id: str = "default",
        first_seen_paper: str = "",
        **extra_props,
    ) -> None:
        """创建或更新实体节点.

        实体按 (name, entity_type, project_id) 唯一标识。
        使用 MERGE 避免重复创建，同时递增 occurrence_count。
        """
        cypher = """
        MERGE (e:Entity {name: $name, entity_type: $entity_type, project_id: $project_id})
        ON CREATE SET
            e.occurrence_count = 1,
            e.first_seen_paper = $first_seen_paper,
            e.created_at = datetime(),
            e.updated_at = datetime()
        ON MATCH SET
            e.occurrence_count = COALESCE(e.occurrence_count, 0) + 1,
            e.updated_at = datetime()
        SET e += $extra_props
        """
        with self.session() as sess:
            sess.run(
                cypher,
                {
                    "name": name,
                    "entity_type": entity_type,
                    "project_id": project_id,
                    "first_seen_paper": first_seen_paper,
                    "extra_props": extra_props,
                },
            )

    # ------------------------------------------------------------------
    # 关系 / 三元组写入
    # ------------------------------------------------------------------

    def upsert_triple(
        self,
        triple: Triple,
        *,
        project_id: str = "default",
        paper_id: str = "",
    ) -> None:
        """写入单个三元组: 确保两端实体存在，然后创建关系.

        关系属性:
          - evidence: 原文摘录（溯源核心）
          - confidence: 抽取置信度
          - paper_id: 来源论文
          - project_id: 项目隔离
          - source_chunk_id: chunk 来源
        """
        # 论文级关系必须连接真实的 Paper 节点，不能把论文属性写成
        # Entity -> Entity 的自循环。
        if triple.head_type == "Paper":
            self.upsert_entity(
                triple.tail, triple.tail_type,
                project_id=project_id, first_seen_paper=paper_id,
            )
            cypher = """
            MERGE (p:Paper {doi: $paper_id, project_id: $project_id})
            WITH p
            MATCH (t:Entity {name: $tail, entity_type: $tail_type, project_id: $project_id})
            MERGE (p)-[r:RELATES {relation_type: $relation, paper_id: $paper_id}]->(t)
            ON CREATE SET
                r.evidence = $evidence,
                r.confidence = $confidence,
                r.project_id = $project_id,
                r.created_at = datetime(),
                r.new_type_suggestion = $new_type_suggestion,
                r.source_chunk_id = $source_chunk_id
            ON MATCH SET
                r.evidence = r.evidence + ' | ' + $evidence,
                r.confidence = CASE
                    WHEN $confidence > COALESCE(r.confidence, 0) THEN $confidence
                    ELSE r.confidence
                END,
                r.updated_at = datetime()
            """
            with self.session() as sess:
                sess.run(cypher, {
                    "paper_id": paper_id,
                    "tail": triple.tail,
                    "tail_type": triple.tail_type,
                    "relation": triple.relation,
                    "evidence": triple.evidence,
                    "confidence": triple.confidence,
                    "project_id": project_id,
                    "new_type_suggestion": triple.new_type_suggestion,
                    "source_chunk_id": triple.source_chunk_id,
                })
            return

        # Step 1: 确保实体存在
        self.upsert_entity(
            triple.head, triple.head_type,
            project_id=project_id, first_seen_paper=paper_id,
        )
        self.upsert_entity(
            triple.tail, triple.tail_type,
            project_id=project_id, first_seen_paper=paper_id,
        )

        # Step 2: 创建关系
        # MERGE 关系按类型 + 两端节点 + paper_id 去重
        cypher = """
        MATCH (h:Entity {name: $head, entity_type: $head_type, project_id: $project_id})
        MATCH (t:Entity {name: $tail, entity_type: $tail_type, project_id: $project_id})
        MERGE (h)-[r:RELATES {relation_type: $relation, paper_id: $paper_id}]->(t)
        ON CREATE SET
            r.evidence = $evidence,
            r.confidence = $confidence,
            r.project_id = $project_id,
            r.created_at = datetime(),
            r.new_type_suggestion = $new_type_suggestion,
            r.source_chunk_id = $source_chunk_id
        ON MATCH SET
            r.evidence = r.evidence + ' | ' + $evidence,
            r.confidence = CASE
                WHEN $confidence > COALESCE(r.confidence, 0) THEN $confidence
                ELSE r.confidence
            END,
            r.updated_at = datetime()
        """
        with self.session() as sess:
            sess.run(
                cypher,
                {
                    "head": triple.head,
                    "head_type": triple.head_type,
                    "tail": triple.tail,
                    "tail_type": triple.tail_type,
                    "relation": triple.relation,
                    "evidence": triple.evidence,
                    "confidence": triple.confidence,
                    "project_id": project_id,
                    "paper_id": paper_id,
                    "new_type_suggestion": triple.new_type_suggestion,
                    "source_chunk_id": triple.source_chunk_id,
                },
            )

    def upsert_triples_batch(
        self,
        triples: list[Triple],
        *,
        project_id: str = "default",
        paper_id: str = "",
        batch_size: int = 50,
    ) -> int:
        """真实批量写入三元组 —— 使用 UNWIND 减少网络往返.

        使用单个 session，不为每个三元组建立独立连接。
        实体和关系都通过 UNWIND 批量操作。
        写入是幂等的（MERGE 语义）。

        Args:
            triples: 三元组列表
            project_id: 项目 ID
            paper_id: 来源论文 ID
            batch_size: 每批 UNWIND 的三元组数

        Returns:
            写入的三元组总数
        """
        count = 0
        with self.session() as sess:
            for i in range(0, len(triples), batch_size):
                batch = triples[i : i + batch_size]

                # 构建 UNWIND 参数
                entities = []
                rels = []
                paper_rels = []
                seen_entities: set[tuple[str, str]] = set()
                for t in batch:
                    if t.head_type != "Paper":
                        hk = (t.head, t.head_type)
                        if hk not in seen_entities:
                            seen_entities.add(hk)
                            entities.append({
                                "name": t.head, "entity_type": t.head_type,
                                "project_id": project_id, "paper_id": paper_id,
                            })
                    tk = (t.tail, t.tail_type)
                    if tk not in seen_entities:
                        seen_entities.add(tk)
                        entities.append({
                            "name": t.tail, "entity_type": t.tail_type,
                            "project_id": project_id, "paper_id": paper_id,
                        })
                    rel = {
                        "head": t.head, "head_type": t.head_type,
                        "tail": t.tail, "tail_type": t.tail_type,
                        "relation": t.relation, "evidence": t.evidence,
                        "confidence": t.confidence,
                        "project_id": project_id, "paper_id": paper_id,
                        "new_type_suggestion": t.new_type_suggestion or "",
                        "source_chunk_id": t.source_chunk_id,
                    }
                    if t.head_type == "Paper":
                        paper_rels.append(rel)
                    else:
                        rels.append(rel)

                # Step 1: 批量 MERGE 实体
                if entities:
                    sess.run(
                        """
                        UNWIND $entities AS ent
                        MERGE (e:Entity {name: ent.name, entity_type: ent.entity_type, project_id: ent.project_id})
                        ON CREATE SET
                            e.occurrence_count = 1,
                            e.first_seen_paper = ent.paper_id,
                            e.created_at = datetime(),
                            e.updated_at = datetime()
                        ON MATCH SET
                            e.occurrence_count = COALESCE(e.occurrence_count, 0) + 1,
                            e.updated_at = datetime()
                        """,
                        {"entities": entities},
                    )

                # Step 2: Entity -> Entity 关系
                result = sess.run(
                    """
                    UNWIND $rels AS rel
                    MATCH (h:Entity {name: rel.head, entity_type: rel.head_type, project_id: rel.project_id})
                    MATCH (t:Entity {name: rel.tail, entity_type: rel.tail_type, project_id: rel.project_id})
                    WITH h, t, rel
                    MERGE (h)-[r:RELATES {relation_type: rel.relation, paper_id: rel.paper_id}]->(t)
                    ON CREATE SET
                        r.evidence = rel.evidence,
                        r.confidence = rel.confidence,
                        r.project_id = rel.project_id,
                        r.created_at = datetime(),
                        r.new_type_suggestion = rel.new_type_suggestion,
                        r.source_chunk_id = rel.source_chunk_id
                    ON MATCH SET
                        r.evidence = r.evidence + ' | ' + rel.evidence,
                        r.confidence = CASE
                            WHEN rel.confidence > COALESCE(r.confidence, 0) THEN rel.confidence
                            ELSE r.confidence
                        END,
                        r.updated_at = datetime()
                    RETURN count(r) AS cnt
                    """,
                    {"rels": rels},
                )
                record = result.single()
                if record:
                    count += record["cnt"]

                # Step 3: Paper -> Entity 论文级关系
                if paper_rels:
                    result = sess.run(
                        """
                        UNWIND $rels AS rel
                        MERGE (p:Paper {doi: rel.paper_id, project_id: rel.project_id})
                        WITH p, rel
                        MATCH (t:Entity {name: rel.tail, entity_type: rel.tail_type, project_id: rel.project_id})
                        MERGE (p)-[r:RELATES {relation_type: rel.relation, paper_id: rel.paper_id}]->(t)
                        ON CREATE SET
                            r.evidence = rel.evidence,
                            r.confidence = rel.confidence,
                            r.project_id = rel.project_id,
                            r.created_at = datetime(),
                            r.new_type_suggestion = rel.new_type_suggestion,
                            r.source_chunk_id = rel.source_chunk_id
                        ON MATCH SET
                            r.evidence = r.evidence + ' | ' + rel.evidence,
                            r.confidence = CASE
                                WHEN rel.confidence > COALESCE(r.confidence, 0) THEN rel.confidence
                                ELSE r.confidence
                            END,
                            r.updated_at = datetime()
                        RETURN count(r) AS cnt
                        """,
                        {"rels": paper_rels},
                    )
                    record = result.single()
                    if record:
                        count += record["cnt"]

        return count

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def query_entity(
        self,
        name: str,
        *,
        project_id: str = "default",
        entity_type: Optional[str] = None,
    ) -> list[dict]:
        """按名称查询实体节点."""
        cypher = """
        MATCH (e:Entity {name: $name, project_id: $project_id})
        """
        if entity_type:
            cypher += " WHERE e.entity_type = $entity_type"

        cypher += """
        OPTIONAL MATCH (e)-[r:RELATES]-(other:Entity)
        RETURN e, r, other
        LIMIT 50
        """
        params: dict = {"name": name, "project_id": project_id}
        if entity_type:
            params["entity_type"] = entity_type

        with self.session() as sess:
            results = list(sess.run(cypher, params))
            return [dict(r) for r in results]

    def query_evidence(
        self,
        subgraph_label: str = "",
        *,
        project_id: str = "default",
        entity_type: Optional[str] = None,
        relation_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """按标签/类型检索三元组（供 retriever.global_retrieve 调用）.

        Args:
            subgraph_label: 模糊匹配实体名称
            project_id: 项目 ID
            entity_type: 筛选实体类型
            relation_type: 筛选关系类型
            limit: 返回数量上限

        Returns:
            [{head, head_type, relation, tail, tail_type, evidence, confidence, paper_id}, ...]
        """
        cypher = """
        MATCH (h {project_id: $project_id})
        """
        if entity_type:
            cypher += " WHERE h.entity_type = $entity_type"

        cypher += """
        MATCH (h)-[r:RELATES]->(t:Entity {project_id: $project_id})
        """
        conditions = []
        if subgraph_label:
            conditions.append(
                "(h.name CONTAINS $label OR t.name CONTAINS $label)"
            )
        if relation_type:
            conditions.append("r.relation_type = $relation_type")

        if conditions:
            cypher += " WHERE " + " AND ".join(conditions)

        cypher += """
        RETURN
            COALESCE(h.name, h.doi) AS head,
            COALESCE(h.entity_type, 'Paper') AS head_type,
            r.relation_type AS relation,
            t.name AS tail,
            t.entity_type AS tail_type,
            r.evidence AS evidence,
            r.confidence AS confidence,
            r.paper_id AS paper_id,
            r.source_chunk_id AS source_chunk_id
        ORDER BY r.confidence DESC
        LIMIT $limit
        """
        params: dict = {
            "project_id": project_id,
            "label": subgraph_label,
            "relation_type": relation_type,
            "entity_type": entity_type,
            "limit": limit,
        }
        with self.session() as sess:
            results = list(sess.run(cypher, params))
            return [dict(r) for r in results]

    def query_paper_triples(
        self,
        paper_id: str,
        *,
        project_id: str = "default",
    ) -> list[dict]:
        """查询某篇论文的所有三元组."""
        cypher = """
        MATCH (h {project_id: $project_id})
        -[r:RELATES {paper_id: $paper_id}]->
        (t:Entity {project_id: $project_id})
        RETURN
            COALESCE(h.name, h.doi) AS head,
            COALESCE(h.entity_type, 'Paper') AS head_type,
            r.relation_type AS relation,
            t.name AS tail, t.entity_type AS tail_type,
            r.evidence AS evidence, r.confidence AS confidence,
            r.source_chunk_id AS source_chunk_id
        ORDER BY r.confidence DESC
        """
        with self.session() as sess:
            results = list(sess.run(cypher, {"project_id": project_id, "paper_id": paper_id}))
            return [dict(r) for r in results]

    def get_stats(
        self,
        *,
        project_id: str = "default",
    ) -> dict:
        """获取图谱统计信息."""
        stats = {}
        with self.session() as sess:
            # 论文数
            r = sess.run(
                "MATCH (p:Paper {project_id: $pid}) RETURN count(p) AS cnt",
                {"pid": project_id},
            ).single()
            stats["paper_count"] = r["cnt"] if r else 0

            # 实体数
            r = sess.run(
                "MATCH (e:Entity {project_id: $pid}) RETURN count(e) AS cnt",
                {"pid": project_id},
            ).single()
            stats["entity_count"] = r["cnt"] if r else 0

            # 关系数
            r = sess.run(
                "MATCH ()-[r:RELATES {project_id: $pid}]->() RETURN count(r) AS cnt",
                {"pid": project_id},
            ).single()
            stats["relation_count"] = r["cnt"] if r else 0

            # 按实体类型分布
            r = sess.run(
                """
                MATCH (e:Entity {project_id: $pid})
                RETURN e.entity_type AS type, count(e) AS cnt
                ORDER BY cnt DESC
                """,
                {"pid": project_id},
            )
            stats["entity_type_distribution"] = {
                rec["type"]: rec["cnt"] for rec in r
            }

            # Concept 占比（自举指标）
            concept_total = stats["entity_type_distribution"].get("Concept", 0)
            stats["bootstrapping_ratio"] = (
                concept_total / stats["entity_count"]
                if stats["entity_count"] > 0
                else 0.0
            )

        return stats

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def clear_project(self, project_id: str) -> dict:
        """清除指定项目的所有节点和关系.

        只删除指定 project_id 的数据，不影响其他项目。

        危险操作，谨慎使用。
        """
        with self.session() as sess:
            r = sess.run(
                """
                MATCH (n {project_id: $pid})
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                {"pid": project_id},
            )
            record = r.single()
            return {"deleted_nodes": record["deleted"] if record else 0}
