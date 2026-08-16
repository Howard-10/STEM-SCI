# Physics-STEM 混合检索与轻量 GraphRAG：实施审计

> 审计日期：2026-08-12
> 范围：共享 Physics-STEM 语料的身份解析、图导航、原文检索、ContextBundle 边界与可复现性。

## 结论

本轮已将原本彼此分离的论文级稀疏图、段落级向量资产和正式 Context MVP 接为一个**可运行但仍受边界限制**的后端能力：

```text
SparsePaperGraph（候选导航）
→ PaperIdentityResolver（论文级桥接）
→ Dense / BM25 原文段落检索
→ RRF（仅 dense + sparse）
→ Discovery ContextBundle
```

它不是 Microsoft GraphRAG 的完整实现，也不是可以直接支撑正式论文结论的证据系统。正式模式目前按设计失败关闭，因为尚未发布可验证的“切片 → 原始 PDF 页码/字符位置”定位索引，也尚未对共享语料摘录完成来源核验。

## 已验证资产

| 项目 | 实测结果 | 结论 |
|---|---:|---|
| 共享论文 PDF | 122 | 本地受控；Git 忽略 |
| 向量 metadata | 1,788 chunks | 本地受控；可由运行时重建 BM25 |
| FAISS | 1,788 entries、1024 维声明 | 资产存在；本机环境缺少 FAISS/DashScope，因而本次真实运行降级 |
| 稀疏图 | 122 profiles、944 triples | 已读取并用于候选导航 |
| 图三元组状态 | 全部 `model_generated_unverified` | 只可导航，不可作为论文证据 |
| 论文身份图谱 | 122 条映射；50 条带 DOI、72 条无 DOI | DOI 非主键；使用受控 `paper_id` 初始化历史 CanonicalPaper |

## 实现结果

### 1. 身份和资产安全

- 新增 `CanonicalPaper`，与 `SourceDocument` 的文件 SHA 分离。
- 已禁止从标题相似度自动合并论文；受控历史库按 `graph_paper_id` 初始化稳定身份。
- 新增 `physics_stem_v1.manifest.json`，核验身份映射、图 JSON、向量 metadata 和 FAISS 文件的 SHA256。
- 若必须资产 hash 不一致，Discovery 直接返回 `UNAVAILABLE`；不会输出看似可信的陈旧检索结果。

### 2. GraphRAG 边界

- `GraphRetriever` 只读 `SparsePaperGraph`，最多返回 20 篇候选、单跳 facet 匹配、不调用 LLM、不写图。
- 它返回命中的主题和边 ID 作为导航解释。
- 图导航分数绝不进入 RRF；RRF 只使用 dense/sparse 的 rank。
- 图故障自动退化到文本检索，并在 `retrieval_trace` 明示风险。

### 3. 原文检索和上下文

- 新 `SparseRetriever` 从 metadata 原文运行时构建真实 BM25（`k1=1.2`、`b=0.75`），不加载旧的误名 TF-IDF pickle。
- `DenseRetriever` 是可选 FAISS + DashScope 查询 embedding 适配器；只发送用户查询，不发送整库 PDF。
- 每篇论文最多进入两个 chunk；上下文按 token budget 裁剪。
- Discovery Bundle 可包含 `model_generated_unverified` 的可追踪检索候选，但必须带风险和 provenance。
- Formal Bundle 没有合格页码定位和 `source_verified`/`human_verified` Evidence 时返回空证据并标记 `insufficient_verified_evidence`。

### 4. LangGraph 边界

本轮没有新增 LangGraph `StateGraph`。检索层只实现 `HybridContextProvider`；未来若使用 LangGraph，只能让其调用 Controller 批准的动作。Retriever、GraphRAG、Agent 和 Reviewer 不拥有 `current_stage` 修改权。

## 自动化验证

本轮新增和运行的检索/Context 验收包括：

```text
身份不由 PDF SHA 建立、DOI 可归一化、标题+错误年份不自动合并
共享资产在无 locator 时 Discovery 可用而 Formal 被阻塞
图导航有上限且维持 model_generated_unverified
BM25 在运行时由 metadata 重建，结果有稳定 rank
图导航分数不改变 RRF 分数
图不可用时退化 sparse-only，且不伪装 hybrid
Discovery Bundle 可追踪；Formal Bundle 缺定位时 fail closed
asset hash 改变时 Discovery 不放行
API 不返回绝对本地路径
原本的 Context MVP 仍保留 local_keyword 行为
```

定向检查结果：Ruff 通过；Mypy 通过；`test_knowledge_hybrid_retrieval.py` 共 15 项通过；完整后端测试集 189 项通过；`compileall`、包导入、前端类型检查和前端生产构建通过。检索 API 的 OpenAPI 已由当前 FastAPI 应用重新导出；三个共享语料接口均使用显式响应模型，而不是宽泛的字典响应。

### 本次状态修正

最初的计划把 `GraphRetriever → HybridRetriever → ContextBundle` 写为“未实施”。该表述在本轮代码落地后已经不再准确，现修正为：

```text
已实施：图导航增强的发现型混合检索
仍未实施：完整 Microsoft GraphRAG；可正式引用的图/向量证据链；LangGraph StateGraph 工作流
```

具体而言，`GraphRetriever` 读取已版本化的 122 篇论文、944 条三元组的稀疏论文图，只把候选论文及命中 facet 交给 `HybridRetriever`；它不调用 LLM、不写图、不修改 RRF 分数。`HybridRetriever` 再以可用的 dense/sparse 文本检索寻找原文切片，并将检索模式、图可用性和降级风险写入 `RetrievalTrace`。只有实际被图导航命中的论文才会获得 `graph_navigation` 标记。正式模式因缺少定位索引与核验原文而继续 fail-closed。

前端“证据与上下文”工作区已增加共享 Physics-STEM 语料入口：可查看语料状态、在发现模式搜索、查看图候选与文本命中、构建带 manifest/trace 的 Discovery ContextBundle；正式模式在未满足定位和核验条件时禁用。

## 真实语料演示结果

对中文查询“生成式AI支架物理建模师范生”执行真实本地资产检索：

```text
Discovery readiness: READY
Formal readiness: BLOCKED（缺 formal locator index）
Graph candidates: 20
文本结果: 5
实际运行模式: SPARSE_ONLY
降级原因: 本机 Python 环境缺少 faiss-cpu / DashScope 运行依赖
Discovery ContextBundle: 已生成，含 3 条未核验候选 Evidence
Formal ContextBundle: 0 条 Evidence，fail-closed
```

这说明系统没有以“GraphRAG”之名绕过原文定位或核验。但该真实检索结果尚未经过 Gold Set 质量验收，不能宣称检索相关性已达标。

## 外部资料复核后的设计判断

RAG 的基础价值是将可更新、可追溯的非参数资料检索进生成上下文，而不是把事实只寄托在模型参数中。[Lewis 等人的 RAG 论文](https://arxiv.org/abs/2005.11401)也将显式检索索引作为非参数记忆来处理。

Microsoft GraphRAG 的 Local Search 同时使用图结构和原始文档 text units；其完整 indexing pipeline 还包括实体/关系/claim 抽取、社区发现、社区报告与向量嵌入。[GraphRAG Local Search](https://microsoft.github.io/graphrag/query/local_search/) [GraphRAG Indexing Overview](https://microsoft.github.io/graphrag/index/overview/) 因此，本项目的“图导航 + 原文 chunk”方向是合理的轻量近似，但不能将其误称为完整 Microsoft GraphRAG，也不应在 122 篇语料规模上先投入昂贵的社区报告与全局 map-reduce 检索。

网络发现层可先使用 Crossref 的 `works`/`query.bibliographic` 接口来发现候选题录；其返回仅是候选元数据，不是可用于正式论证的全文 Evidence。[Crossref REST API](https://api.crossref.org/swagger-ui/index.html)

## 仍未完成，且不能跳过

| 优先级 | 缺口 | 后果 | 下一步 |
|---|---|---|---|
| P0 | 每个共享 chunk 到 PDF 页码/字符位置的 locator index | Formal ContextBundle 不能合法引用原文 | 从 122 PDF 的逐页文本构建、人工抽样核验 locator |
| P0 | 关键 Evidence 的 source verification | 不能支撑正式研究设计或写作 | 建立人工核验队列和审批记录 |
| P1 | 安装并锁定 FAISS / DashScope 运行依赖，或迁移到新的本地 embedding 索引 | 当前真实检索是 sparse-only | 在隔离环境安装，核验 1024 维、1,788 条、manifest hash |
| P1 | 20 题 Gold Set 的双人标注 | 无法声称图导航提升检索质量 | 填写 `data/evaluation/physics_stem_v1_retrieval_gold.json` 并冻结版本 |
| P2 | `LiteratureDiscoveryOperator` | 语料不足时只能人工补充 | 接 Crossref + OpenAlex 的候选发现；不自动下载全文 |
| P2 | LangGraph | 当前可用的是 Controller 自身的确定性流程 | 在 Controller 权力边界稳定后单独接入 |

## 可对外表述与禁止表述

可以说：

> STEM-SCI 已实现论文级关系图导航和段落级混合检索的后端基础：图谱用于发现关联研究，检索器用于寻找原文候选，系统会记录资产版本、检索轨迹和降级状态；正式 ContextBundle 在证据定位与核验不足时会拒绝放行。

不能说：

```text
“完整 GraphRAG 已完成”
“共享 122 篇论文已成为可直接引用的正式知识库”
“系统已完成 LangGraph 多 Agent 工作流”
“当前真实运行已经通过向量+图谱双路检索”
```
