"""RAG Orchestrator —— 统一检索编排层.

将大语言模型、图数据库(Neo4j)、向量库(FAISS+BM25)串联起来，
由 LLM 自动判断查询策略，合成带溯源的答案。

使用方式:
    from rag_orchestrator import RAGPipeline

    pipeline = RAGPipeline()
    result = pipeline.answer("项目式学习对物理概念理解有什么效果？")
    print(result.answer)
    for c in result.citations:
        print(c.paper_title, c.evidence)
"""

from .pipeline import RAGPipeline
from .config import LLMConfig

__all__ = ["RAGPipeline", "LLMConfig"]
