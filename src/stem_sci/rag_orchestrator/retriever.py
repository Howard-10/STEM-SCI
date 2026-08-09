"""统一检索层 —— 封装向量库和图数据库的查询接口.

提供 4 个检索函数，供 tool_registry 注册:
    - vector_search(query, top_k)      → 向量库全文检索
    - graph_query(keyword, ...)        → 图谱关系查询
    - paper_lookup(paper_id)           → 论文精确查找
    - hybrid_search(query, keyword)    → 混合并行检索
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ===========================================================================
# 路径配置 —— 找到 vector_kb 和 graph_rag 模块
# ===========================================================================

_SELF_DIR = Path(__file__).resolve().parent  # rag_orchestrator/
_STEM_SCI_DIR = _SELF_DIR.parent             # stem_sci/

# vector_kb: 使用 importlib 加载
_VECTOR_KB_QUERY_PATH = _STEM_SCI_DIR / "vector_kb" / "query.py"

# graph_rag: 在 stem_sci 目录下
if str(_STEM_SCI_DIR) not in sys.path:
    sys.path.insert(0, str(_STEM_SCI_DIR))


_VECTOR_KB_DIR = _VECTOR_KB_QUERY_PATH.parent  # vector_kb/ 目录


# ===========================================================================
# Paper ID 归一化 —— 统一向量库和图库的论文标识符
# ===========================================================================


def normalize_paper_id(value: str) -> dict[str, str]:
    """将任意格式的论文标识符归一化为 {paper_id, doi}.

    输入可能是:
      - paper_id:  "01_AIMS_10.3934_steme.2026023"
      - filename:  "01_AIMS_10.3934_steme.2026023.pdf"
      - doi:       "10.3934/steme.2026023"
      - doi(点):   "10.3934.steme.2026023"

    Returns:
      {"paper_id": "01_AIMS_10.3934_steme.2026023", "doi": "10.3934/steme.2026023"}
    """
    v = str(value).strip().removesuffix(".pdf")

    # 判断是 paper_id 格式 (包含 _AIMS_ 等期刊前缀) 还是纯 DOI
    if v.startswith("10."):
        # 纯 DOI: 10.3934/steme.2026023 或 10.3934.steme.2026023
        # 将 10.3934.steme.2026023 → 10.3934/steme.2026023
        if "/" not in v:
            # 找到第二个 . 的位置，替换为 /
            idx = v.find(".", v.find(".") + 1)
            if idx > 0:
                doi = v[:idx] + "/" + v[idx+1:]
            else:
                doi = v
        else:
            doi = v
        return {"paper_id": "", "doi": doi}
    else:
        # paper_id 格式: 01_AIMS_10.3934_steme.2026023
        paper_id = v
        # 提取 DOI: 去掉 "序号_期刊_" 前缀，把第一个 _ 换成 /
        parts = v.split("_", 2)  # ["01", "AIMS", "10.3934_steme.2026023"]
        if len(parts) >= 3:
            doi_raw = parts[2]  # "10.3934_steme.2026023"
            # 把第一个 _ 替换为 /（DOI 格式）
            doi = doi_raw.replace("_", "/", 1)  # "10.3934/steme.2026023"
        else:
            doi = v
        return {"paper_id": paper_id, "doi": doi}


def _load_vector_kb_module():
    """动态加载 vector_kb/query.py."""
    path = str(_VECTOR_KB_QUERY_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"vector_kb query.py not found at: {path}")
    spec = importlib.util.spec_from_file_location("vector_kb_query", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["vector_kb_query"] = module
    spec.loader.exec_module(module)
    return module


# ===========================================================================
# Neo4j 连接（延迟加载）
# ===========================================================================

_neo4j_store = None


def _get_graph_store():
    """获取 Neo4j GraphStore 单例."""
    global _neo4j_store
    if _neo4j_store is None:
        from graph_rag.graph_store import GraphStore

        _neo4j_store = GraphStore.from_env()
    return _neo4j_store


# ===========================================================================
# 数据结构
# ===========================================================================


class ChunkResult(dict):
    """向量检索结果."""
    pass


class TripleResult(dict):
    """图谱检索结果."""
    pass


# ===========================================================================
# 1. vector_search —— 向量库全文检索
# ===========================================================================


def vector_search(query: str, top_k: int = 5) -> list[dict]:
    """在论文全文中搜索相关段落.

    Args:
        query: 检索查询（中文或英文）
        top_k: 返回结果数

    Returns:
        [{rank, score, text, paper_title, doi, year, section_hint, chunk_id}, ...]
    """
    try:
        # vector_kb 使用相对路径读写 vectordb/ 文件，需要在其目录下执行
        old_cwd = os.getcwd()
        os.chdir(str(_VECTOR_KB_DIR))
        try:
            vk = _load_vector_kb_module()
            searcher = vk.HybridSearcher()
            raw_results = searcher.search(query, top_k=top_k)
        finally:
            os.chdir(old_cwd)

        results = []
        for rank, (idx, score, meta) in enumerate(raw_results):
            # 归一化标识符
            file_name = meta.get("filename", "")
            doi = meta.get("doi", "")
            normalized = normalize_paper_id(file_name if file_name else doi)
            results.append({
                "rank": rank + 1,
                "score": round(score, 4),
                "text": meta.get("text", "")[:600],
                "paper_title": meta.get("paper_title", ""),
                "doi": normalized["doi"] or doi,
                "paper_id": normalized["paper_id"] or file_name,
                "year": meta.get("year", ""),
                "journal": meta.get("journal", ""),
                "section_hint": meta.get("section_hint", ""),
                "chunk_id": meta.get("chunk_id", ""),
            })

        return results
    except FileNotFoundError:
        return [{"error": "向量库文件未找到，请确认 vector_kb(1)/vector_kb/vectordb/ 路径正确"}]
    except Exception as e:
        return [{"error": f"向量检索失败: {str(e)}"}]


# ===========================================================================
# 2. graph_query —— 图谱关系查询
# ===========================================================================


def graph_query(
    keyword: str,
    entity_type: str = "",
    relation_type: str = "",
    limit: int = 15,
    project_id: str = "stem-sci",
) -> list[dict]:
    """查询知识图谱中的关系.

    Args:
        keyword: 检索关键词
        entity_type: 可选，筛选实体类型
        relation_type: 可选，筛选关系类型
        limit: 返回结果数
        project_id: Neo4j 项目 ID

    Returns:
        [{head, head_type, relation, tail, tail_type, evidence, confidence, paper_id}, ...]
    """
    try:
        store = _get_graph_store()

        # 使用 query_evidence 做模糊匹配
        triples = store.query_evidence(
            subgraph_label=keyword,
            project_id=project_id,
            entity_type=entity_type or None,
            relation_type=relation_type or None,
            limit=limit,
        )

        # 去重 + 按置信度排序
        seen = set()
        results = []
        for t in triples:
            key = (t.get("head"), t.get("relation"), t.get("tail"))
            if key in seen:
                continue
            seen.add(key)
            pid = t.get("paper_id", "")
            normalized = normalize_paper_id(pid)
            results.append({
                "head": t.get("head", ""),
                "head_type": t.get("head_type", ""),
                "relation": t.get("relation", ""),
                "tail": t.get("tail", ""),
                "tail_type": t.get("tail_type", ""),
                "evidence": (t.get("evidence") or "")[:300],
                "confidence": t.get("confidence", 0.0),
                "paper_id": normalized["paper_id"] or pid,
                "doi": normalized["doi"],
            })

        # 同时查询论文元数据（按标题关键词）
        paper_results = _search_papers_by_keyword(keyword, project_id, limit=5)
        for p in paper_results:
            # 避免重复
            results.append({
                "head": p.get("doi", ""),
                "head_type": "Paper",
                "relation": "PAPER_MATCH",
                "tail": p.get("title", ""),
                "tail_type": "Paper",
                "evidence": f"{p.get('journal', '')} ({p.get('year', '')}) — {p.get('authors', '')}",
                "confidence": 1.0,
                "paper_id": p.get("doi", ""),
            })

        return results
    except Exception as e:
        return [{"error": f"图谱查询失败: {str(e)}"}]


def _search_papers_by_keyword(
    keyword: str, project_id: str, limit: int = 5
) -> list[dict]:
    """按关键词搜索论文元数据."""
    try:
        store = _get_graph_store()
        with store.session() as sess:
            cypher = """
            MATCH (p:Paper {project_id: $pid})
            WHERE p.title CONTAINS $kw OR p.doi CONTAINS $kw
            RETURN p.doi AS doi, p.title AS title, p.year AS year,
                   p.journal AS journal, p.authors AS authors
            LIMIT $limit
            """
            result = sess.run(
                cypher, {"pid": project_id, "kw": keyword, "limit": limit}
            )
            return [dict(r) for r in result]
    except Exception:
        return []


# ===========================================================================
# 3. paper_lookup —— 论文精确查找
# ===========================================================================


def paper_lookup(paper_id: str, project_id: str = "stem-sci") -> dict:
    """精确查找一篇论文的详细信息和所有三元组.

    Args:
        paper_id: DOI 或 paper_id
        project_id: Neo4j 项目 ID

    Returns:
        {paper: {doi, title, year, journal, authors}, triples: [...], triple_count: N}
    """
    try:
        store = _get_graph_store()
        normalized = normalize_paper_id(paper_id)
        doi = normalized["doi"]
        pid = normalized["paper_id"] or paper_id

        # 查论文元数据（同时匹配 doi 和 paper_id 格式）
        with store.session() as sess:
            cypher = """
            MATCH (p:Paper {project_id: $pid})
            WHERE p.doi = $doi1 OR p.doi = $doi2 OR p.doi = $paper_id OR p.doi CONTAINS $paper_id
            RETURN p.doi AS doi, p.title AS title, p.year AS year,
                   p.journal AS journal, p.authors AS authors
            LIMIT 1
            """
            result = sess.run(
                cypher, {
                    "pid": project_id,
                    "doi1": doi,
                    "doi2": paper_id,
                    "paper_id": pid,
                }
            )
            paper_rec = result.single()
            paper_info = dict(paper_rec) if paper_rec else {"doi": doi or paper_id}

        # 查三元组（用 paper_id 格式，因为 triple 的 paper_id 字段用这个格式）
        triples = store.query_paper_triples(
            paper_id=pid, project_id=project_id
        )
        if not triples:
            # 也尝试用 DOI 查
            triples = store.query_paper_triples(
                paper_id=doi, project_id=project_id
            )

        return {
            "paper": paper_info,
            "triples": [
                {
                    "head": t.get("head"),
                    "head_type": t.get("head_type"),
                    "relation": t.get("relation"),
                    "tail": t.get("tail"),
                    "tail_type": t.get("tail_type"),
                    "evidence": (t.get("evidence") or "")[:300],
                    "confidence": t.get("confidence"),
                }
                for t in triples
            ],
            "triple_count": len(triples),
        }
    except Exception as e:
        return {"error": f"论文查找失败: {str(e)}"}


# ===========================================================================
# 4. hybrid_search —— 混合并行检索
# ===========================================================================


def hybrid_search(
    query: str, keyword: str = "", top_k: int = 5, graph_limit: int = 10
) -> dict:
    """并行执行向量检索和图谱查询，合并结果.

    Args:
        query: 向量检索查询
        keyword: 图谱关键词（默认用 query）
        top_k: 向量结果数
        graph_limit: 图谱结果数

    Returns:
        {vector_results: [...], graph_results: [...], merged_summary: str}
    """
    kw = keyword or query

    # 并行执行（简单实现: 顺序但快）
    t0 = time.monotonic()
    vector_results = vector_search(query, top_k=top_k)
    t1 = time.monotonic()
    graph_results = graph_query(kw, limit=graph_limit)
    t2 = time.monotonic()

    vector_ms = (t1 - t0) * 1000
    graph_ms = (t2 - t1) * 1000

    # 提取共同涉及的论文（用归一化后的 doi 和 paper_id 交叉匹配）
    vector_dois = set()
    vector_pids = set()
    for r in vector_results:
        d = r.get("doi", "")
        p = r.get("paper_id", "")
        if d:
            vector_dois.add(d)
        if p:
            vector_pids.add(p)

    graph_dois = set()
    graph_pids = set()
    for r in graph_results:
        d = r.get("doi", "")
        p = r.get("paper_id", "")
        if d:
            graph_dois.add(d)
        if p:
            graph_pids.add(p)

    # 按 doi 匹配 + 按 paper_id 匹配
    overlapping_dois = vector_dois & graph_dois
    overlapping_pids = vector_pids & graph_pids
    overlapping_papers = list(overlapping_dois | overlapping_pids)[:10]

    return {
        "vector_results": vector_results,
        "graph_results": graph_results,
        "vector_count": len(vector_results),
        "graph_count": len(graph_results),
        "vector_time_ms": round(vector_ms, 1),
        "graph_time_ms": round(graph_ms, 1),
        "overlapping_papers": overlapping_papers,
    }
