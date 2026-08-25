"""Import the checked-in sparse paper graph into the local Neo4j instance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


def load_rows(path: Path, project_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    entities: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for paper in artifact.get("papers", []):
        paper_id = str(paper.get("paper_id") or "").strip()
        if not paper_id:
            continue
        entities[(paper_id, "Paper")] = {
            "project_id": project_id,
            "name": paper_id,
            "entity_type": "Paper",
            "title": paper.get("title"),
            "source_status": paper.get("source_status"),
        }
        for triple in paper.get("triples", []):
            head = str(triple.get("head") or "").strip()
            tail = str(triple.get("tail") or "").strip()
            head_type = str(triple.get("head_type") or "Entity").strip()
            tail_type = str(triple.get("tail_type") or "Entity").strip()
            relation = str(triple.get("relation") or "RELATED_TO").strip()
            if not head or not tail:
                continue
            entities.setdefault((head, head_type), {
                "project_id": project_id,
                "name": head,
                "entity_type": head_type,
            })
            entities.setdefault((tail, tail_type), {
                "project_id": project_id,
                "name": tail,
                "entity_type": tail_type,
            })
            edges.append({
                "project_id": project_id,
                "head": head,
                "head_type": head_type,
                "tail": tail,
                "tail_type": tail_type,
                "relation_type": relation,
                "evidence": triple.get("evidence"),
                "confidence": triple.get("confidence"),
                "paper_id": paper_id,
                "source_chunk_id": triple.get("source_chunk_id"),
                "layer": triple.get("layer"),
            })
    return list(entities.values()), edges


def import_graph(uri: str, username: str, password: str, database: str,
                 project_id: str, graph_path: Path) -> tuple[int, int]:
    entities, edges = load_rows(graph_path, project_id)
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            session.run(
                """
                CREATE CONSTRAINT entity_identity IF NOT EXISTS
                FOR (e:Entity)
                REQUIRE (e.project_id, e.name, e.entity_type) IS UNIQUE
                """
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {
                    project_id: row.project_id,
                    name: row.name,
                    entity_type: row.entity_type
                })
                SET e.title = coalesce(row.title, e.title),
                    e.source_status = coalesce(row.source_status, e.source_status)
                """,
                rows=entities,
            ).consume()
            session.run(
                """
                UNWIND $rows AS row
                MATCH (h:Entity {
                    project_id: row.project_id,
                    name: row.head,
                    entity_type: row.head_type
                })
                MATCH (t:Entity {
                    project_id: row.project_id,
                    name: row.tail,
                    entity_type: row.tail_type
                })
                MERGE (h)-[r:RELATES {
                    project_id: row.project_id,
                    relation_type: row.relation_type,
                    paper_id: row.paper_id,
                    tail_name: row.tail
                }]->(t)
                SET r.evidence = row.evidence,
                    r.confidence = row.confidence,
                    r.source_chunk_id = row.source_chunk_id,
                    r.layer = row.layer
                """,
                rows=edges,
            ).consume()
    finally:
        driver.close()
    return len(entities), len(edges)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path,
                        default=Path("data/derived/physics_stem/sparse_paper_graph_v2.json"))
    parser.add_argument("--uri", default="bolt://localhost:7688")
    parser.add_argument("--username", default="neo4j")
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", default="neo4j")
    parser.add_argument("--project-id", default="stem-sci")
    args = parser.parse_args()
    entities, edges = import_graph(
        args.uri, args.username, args.password, args.database, args.project_id, args.graph
    )
    print(f"Imported {entities} entities and {edges} relationships")


if __name__ == "__main__":
    main()
