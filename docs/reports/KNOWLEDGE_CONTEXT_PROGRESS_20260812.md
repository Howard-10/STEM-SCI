# STEM-SCI 知识库、检索与 ContextBundle 当前进展

> 更新日期：2026-08-12
> 范围：Physics-STEM 共享知识库、项目私有资料库、混合检索、图谱导航与 ContextBundle
> 当前结论：已具备可演示、可追溯的发现型检索能力；尚未达到可直接支撑正式科研结论的证据库标准。

## 1. 一句话概述

目前已经把“用户上传资料的 Context MVP”“论文段落级向量素材”和“论文级稀疏关系图”接成了一条受控的检索链：图谱用于发现可能相关的论文，文本检索用于返回原文切片，ContextBundle 用于保存有限、带来源与检索轨迹的上下文候选。

系统不能把图谱三元组或模型生成的摘录直接写成论文结论；正式使用仍必须经过原文定位和来源核验。

## 2. 已完成的知识库基础

### 2.1 项目私有资料库（用户上传）

已实现：

- 网页上传 Markdown、TXT、JSON 和可提取文字的 PDF；
- 原文件只读保存，并计算 SHA256；
- 同一项目内按 SHA256 去重；
- 自动将文本切分为 `SourceChunk`；
- SQLite 持久化 `SourceDocument`、`SourceChunk`、`Evidence` 和 `ContextBundle`；
- 按 `project_id` 查询隔离；
- 关键词 Evidence 检索、Evidence 详情、回查原始切片；
- 将证据升级为 `source_verified` 的受控接口；普通接口不能伪造 `human_verified`；
- token 预算下的 ContextBundle 构建与稳定 `context_hash`。

这部分适合每个研究项目补充自己的文献、研究协议、量表说明、教学材料或其他已获授权资料。

### 2.2 Physics-STEM 共享语料

当前受控本地资产为：

| 资产 | 规模 | 用途 |
|---|---:|---|
| 论文 PDF | 122 篇 | 原始受控资料 |
| 段落级文本切片 | 1,788 条 | 原文检索候选 |
| 论文级稀疏关系图 | 122 个 profile、944 条三元组 | 论文关系导航 |
| 论文身份映射 | 122 条 | 统一文件名、DOI、图谱 paper_id 与向量 metadata |

共享语料使用版本化 Manifest 管理。运行前会核验身份表、图谱 JSON、向量 metadata 和 FAISS 索引的 SHA256；关键资产缺失、哈希变化或记录数量不一致时，发现检索会返回 `UNAVAILABLE`，而不是使用可能陈旧的结果。

## 3. 已完成的检索链

当前实现的检索顺序是：

```text
用户问题
  → 透明的中英文术语归一化/扩展
  → GraphRetriever（论文级候选导航）
  → DenseRetriever（可选 FAISS 向量检索）
  → SparseRetriever（运行时真实 BM25 原文检索）
  → RRF（仅融合 dense_rank 与 sparse_rank）
  → 每篇论文最多保留 2 个原文切片
  → Discovery ContextBundle
```

### 3.1 图谱部分做了什么

- `GraphRetriever` 只读取已发布的 `SparsePaperGraph`；
- 最多返回 20 篇论文候选；
- 使用标题、研究方法、教学法、学科领域、研究对象、学习结果、主张等 facet 做单跳导航；
- 返回命中的主题和图边引用，便于解释“为什么推荐这篇论文”；
- 不调用 LLM，不写入图数据库，不修改项目状态；
- 944 条三元组全部为 `model_generated_unverified`，只能导航，不能作为正式 Evidence。

因此，目前 GraphRAG 的准确表述是：**轻量图导航增强检索已实现**，不是完整 Microsoft GraphRAG，也不是已核验的知识图谱证据系统。

### 3.2 RRF 做了什么

RRF 已在代码中实现，公式为：

```text
rrf_score = 1 / (60 + dense_rank) + 1 / (60 + sparse_rank)
```

- 向量和 BM25 都命中的切片，获得两项分数；
- 只在一侧命中时，只保留对应一项；
- 按 RRF 分数、论文 ID、切片序号稳定排序；
- **图谱 `navigation_score` 不进入 RRF**，避免未核验三元组直接改变原文证据排序；
- 只有图谱实际提名的论文，其切片才显示 `graph_navigation` 检索标记。

### 3.3 当前真实运行效果

在当前电脑环境中，真实语料测试结果为：

```text
Discovery 模式：可用
Formal 模式：安全锁定
图谱候选：20 篇
文本命中：5 条
实际检索模式：SPARSE_ONLY
```

现在实际是“图导航 + BM25”。FAISS 与 DashScope 查询 embedding 的适配器已写好，但本机尚未安装其运行依赖并配置查询密钥，因此尚未实际进入“向量 + BM25 → RRF”的双文本通道。系统会明确标记降级，不会把 `SPARSE_ONLY` 伪装为完整混合检索。

## 4. ContextBundle 做了什么

系统现在区分两种上下文：

| 类型 | 用途 | 当前状态 |
|---|---|---|
| `local` | 用户自己上传资料后的项目内检索 | 已可用 |
| `discovery` | 共享 Physics-STEM 语料的探索、选题、找文献候选 | 已可用，但只能使用未核验候选 |
| `formal` | 用于研究设计、写作和正式科研结论的证据上下文 | 当前 fail-closed |

每个共享语料 Discovery ContextBundle 都保存：

- `project_id`、任务引用和查询；
- 被选中的 Evidence 摘录及其 canonical paper/chunk ID；
- 检索模态（图导航、BM25、向量）；
- Manifest 版本与 SHA256 引用；
- token 预算、实际 token 估算和 `context_hash`；
- 降级与核验风险标记。

系统和 Agent 读取的是 Bundle，不是任意 PDF、FAISS 文件、图 JSON 或 API 密钥。Retriever 不能修改 `current_stage`；只有 Controller 能推进研究阶段。

## 5. 前后端与接口

前端“证据与上下文”工作区新增了共享语料区域，可完成：

- 查看共享语料是否就绪；
- 在发现模式检索 Physics-STEM 共享知识库；
- 查看图谱候选论文与文本切片命中；
- 构建带检索轨迹的 Discovery ContextBundle；
- 明确展示正式模式被锁定的原因。

后端已提供：

```text
GET  /api/v1/corpora
GET  /api/v1/corpora/{corpus_id}/manifest
POST /api/v1/retrieval/search
POST /api/v1/context/hybrid-build
```

OpenAPI 已从当前 FastAPI 应用重新导出，并与实际 30 条路由一致。

## 6. 已完成的自检

本轮检查结果：

```text
Ruff：通过
Mypy：通过（120 个源文件）
Pytest：189 passed
Compileall：通过
前端 TypeScript：通过
前端生产构建：通过
OpenAPI：与 FastAPI 当前路由一致
```

检索专项测试覆盖：论文身份解析、Manifest 哈希/数量校验、图谱上限与未核验边界、真实 BM25、RRF 不受图分数影响、图谱故障降级、Formal fail-closed、API 不泄露本地绝对路径和 Gold Set 未冻结时拒绝评估。

## 7. 现在不能宣称完成的内容

以下内容尚未完成，不能在展示或答辩中夸大：

- 不能说“完整 GraphRAG 已完成”；
- 不能说“122 篇论文已全部成为可直接引用的正式知识库”；
- 不能说“当前真实运行已通过向量 + 图谱双路检索”；
- 不能说“LangGraph 多 Agent 工作流已完成”；
- 不能使用 `model_generated_unverified` 三元组或摘录直接写入正式研究结论；
- `project_id` 目前只提供查询隔离，不是账号认证或完整多租户授权。

## 8. 下一步必须做什么

### P0：开放正式 Evidence 前的硬前提

1. 为 1,788 个切片建立 `chunk → PDF 页码/字符位置` 的定位索引；
2. 对关键原文摘录执行人工来源核验，并记录核验人、时间和说明；
3. 在具备定位与核验后，再开放 Formal ContextBundle。

### P1：提升当前检索质量

1. 安装 `faiss-cpu`、`dashscope`、`numpy` 的可选依赖；
2. 配置本地 `DASHSCOPE_API_KEY`，确认查询向量维度为 1024；
3. 验证 1,788 条 metadata 与 FAISS 索引一一对应；
4. 实际运行“向量 + BM25 → RRF”；
5. 由两位成员完成 20 题 Gold Set 的相关性标注、冲突裁决和冻结；
6. 输出 Recall@5、MRR、nDCG 等检索评测结果。

### P2：后续扩展

- 语料不足时增加 Literature Discovery：通过 Crossref/OpenAlex 查找候选元数据，但不自动把网页摘要当正式 Evidence；
- 允许用户继续上传合法拥有或获授权的论文，进入项目私有资料库；
- 在 Controller 权限边界稳定后，再决定是否接入 LangGraph；
- 不需要为了“叫 GraphRAG”而提前部署 Neo4j、社区发现或全局 map-reduce 检索。

## 9. 对组员的推荐表述

> 我们已经实现了 STEM-SCI 的轻量 GraphRAG 知识库原型：论文级关系图负责发现相关研究，段落级原文检索负责寻找可追溯的文本证据，系统会记录语料版本、论文身份、检索路径、风险和 ContextBundle 指纹。当前可用于研究探索和演示；正式科研结论仍须补齐原文页码定位、人工来源核验和检索效果评测。

## 10. 关联材料

- `docs/plans/PHYSICS_STEM_HYBRID_RETRIEVAL_AND_GRAPHRAG_PLAN.md`：完整设计、边界与实施顺序；
- `docs/reports/PHYSICS_STEM_HYBRID_RETRIEVAL_IMPLEMENTATION_AUDIT.md`：实现审计、真实资产验证与未完成事项；
- `data/catalogs/physics_stem/physics_stem_v1.manifest.json`：共享语料资产清单与 SHA256；
- `data/evaluation/physics_stem_v1_retrieval_gold.json`：待双人标注的检索评测集；
- `backend/src/stem_sci/knowledge/`：图导航、BM25、可选向量检索、RRF 和 ContextBundle 实现。
