# GraphRAG 论文关系图层

`graph_rag` 负责构建跨论文的稀疏关系图，不替代 `vector_kb` 的全文证据检索。

## 默认入口：稀疏论文画像

对每篇论文优先调用 `EntityExtractor.extract_sparse_profile`，只把标题、摘要和关键词送给模型：

```python
result = extractor.extract_sparse_profile(
    paper_id="10.xxxx/example",
    title="论文标题",
    abstract="论文摘要",
    keywords="physics education; generative AI",
)
```

该模式最多保留 30 条三元组，默认限制 `RELATED_TO` 不超过 2 条、关键 `CLAIMS` 不超过 5 条，并保留 `_profile` 来源标识。它适合做论文主题、方法、技术、研究对象和结果之间的跨论文导航。

## 全文模式

`extract_from_chunks_batched` 仍然保留，适用于需要段落级证据、统计量和原文追溯的 `EVIDENCE/FULL_AUDIT` 场景。它不应作为整库建图的默认入口。

推荐的两层结构是：

```text
标题/摘要/关键词 → graph_rag（稀疏关系图）
全文切片/原文证据 → vector_kb（向量检索与证据回溯）
```

先用图层定位相关论文和概念，再从 `vector_kb` 取具体片段，避免为每个全文 chunk 都调用一次模型。
