# STEM-SCI Physics-STEM 混合检索、轻量 GraphRAG 与正式 ContextBundle 实施计划（修订版）

> 状态：核心检索链已实施并通过工程自检；正式证据发布仍被定位与人工核验闸门阻塞
> 适用范围：Physics-STEM 共享语料、项目私有补充资料、ContextBundle 检索链
> 非目标：本轮不实现聊天机器人、长期记忆、完整 Microsoft GraphRAG、自动论文下载、Neo4j 生产部署或 LangGraph 工作流迁移。

## 0. 本版修正了什么

本计划以现有真实资产为起点，而不是假设系统已经具备完整 GraphRAG：

```text
本地受控 PDF：122 篇
段落级向量切片：1788 条（FAISS，DashScope text-embedding-v3，1024 维）
论文级稀疏关系图：122 个 Paper Profile、944 条三元组
当前正式后端：SQLite 导入/切片/关键词检索/Evidence/ContextBundle MVP
```

其中 944 条三元组的状态全部是 `model_generated_unverified`。它们可帮助系统理解“哪些论文可能相关、通过什么研究主题相关”，但不是可直接写入科研结论的正式证据。

本版相对旧计划的关键修正：

1. `CanonicalPaper` 不再由 PDF 的 SHA256 派生。SHA256 标识的是**某个文件版本**，不是论文身份；同一论文的出版社 PDF、作者自存档和修订版可能 SHA 不同。
2. 明确区分“项目隔离”与“登录/授权”：已有 `project_id` 是数据查询边界，不是多用户权限系统。
3. 把用户上传、切片、索引、可检索状态拆成独立状态机；不再混用来源导入状态和证据核验状态。
4. 将网络检索定义为“发现候选文献”，不把外部 API 的标题、摘要或模型摘要直接当 Evidence。
5. 现有名为 `bm25.pkl` 的文件实际为 `TfidfVectorizer + CSR matrix`；首版运行时不得继续把它称为 BM25，也不应加载不受控 pickle 作为生产索引。
6. 所有进入正式 ContextBundle 的段落必须能反查到 PDF 页码或等价定位符。无法定位的切片只允许进入 Discovery 模式。
7. 明确 GraphRAG 的首版是“图导航增强的混合检索”，不是 Microsoft GraphRAG 的社区发现、全局报告或二次 LLM 图索引。
8. LangGraph 不作为本轮依赖；后续只允许由 Controller 包装工作流，绝不把阶段控制权下放给检索器或 Agent。

---

## 1. 当前真实基线与结论

### 1.1 当前已存在的东西

| 层次 | 真实状态 | 可以做什么 | 不能声称什么 |
|---|---|---|---|
| Context MVP | SQLite、PDF/TXT/Markdown/JSON 导入、SHA256 去重、切片、关键词检索、证据详情、来源核验、token 预算 ContextBundle | 项目内资料保存与可追溯基础上下文 | 不是向量检索，也不是 GraphRAG |
| 向量库 | 本地 FAISS、1788 段、DashScope `text-embedding-v3` 查询向量 | 原文段落的语义召回 | 还未接入正式 `stem_sci` 后端 |
| 稀疏论文图 | 122 篇论文、944 三元组、证据摘录字段 | 论文主题/方法/人群/结果等的候选导航 | 图中三元组不等于已核验科研事实 |
| `graph_rag/` 目录 | 本地独立原型，包括抽取、schema、Neo4j `GraphStore` | 可继续作为离线构图工具 | 不是已接入产品的 GraphRAG 服务 |
| LangGraph | 未接入 `StateGraph` | 无 | 不能声称已有 LangGraph 多 Agent 工作流 |

### 1.2 对“GraphRAG 有没有实施”的准确回答

答案不是简单的“有”或“没有”，而是三个层次：

```text
论文级三元组抽取原型：已实施
可版本化的 SparsePaperGraph 数据资产：已实施
GraphRetriever → HybridRetriever → Discovery ContextBundle 的轻量产品链：已实施
```

因此，当前最准确的项目表述是：

> STEM-SCI 已完成论文级稀疏关系图的离线构建，并已实施图导航增强的发现型混合检索；尚未完成可用于正式科研结论的 GraphRAG 证据链。

不能说“GraphRAG 已完成”；也不应因为已有 Neo4j 代码就把 Neo4j 当作现有系统依赖。

---

## 2. 本轮目标、输入与硬边界

### 2.1 目标

将“论文级关系导航”与“段落级原文检索”连成一条可复现、可退化、可追溯的链：

```text
中英文研究问题
  → GraphRetriever 发现相关论文候选（导航）
  → DenseRetriever / SparseRetriever 定位原文段落（证据候选）
  → EvidenceSelector 产生带定位的摘录
  → VerificationFilter 按用途筛选
  → DiscoveryContextBundle 或 FormalEvidenceContextBundle
  → Controller / Agent 消费只读上下文
```

### 2.2 不可突破的边界

1. 图谱只参与论文候选导航和检索解释，`navigation_score` 不得同 dense/sparse 分数相加，也不得直接进入 RRF。
2. 正式论文结论只能引用 `source_verified` 或 `human_verified` 的 `EvidenceQuote`；图谱三元组不是正式 Evidence。
3. Agent 只能读取 ContextBundle；不得直接读取 PDF、FAISS、完整向量 metadata、图谱源 JSON、环境变量或 API Key。
4. Controller 是唯一可以修改 `current_stage` 的组件。Retriever、GraphRAG、Agent、Reviewer 都只能返回结构化结果、风险或建议。
5. `ResearchState`、Checkpoint 和图状态只保存工件引用、manifest hash、ID 和摘要，不保存 PDF、向量、完整 chunk 正文或 API 密钥。
6. 图、向量、原始 PDF 与用户私有资料均不可由普通 API 覆盖或删除共享原件。

---

## 3. 语料、论文身份与访问模型

### 3.1 两类语料，不能混为一谈

| 语料类型 | `corpus_id` | 所有权/用途 | 写权限 |
|---|---|---|---|
| 共享基础语料 | `physics_stem_v1` | 122 篇受控 Physics-STEM 文献，用于内部演示和检索评测 | 仅离线发布流程可写；运行时只读 |
| 项目私有语料 | `project:<project_id>` | 用户合法拥有或获授权上传的 PDF、TXT、Markdown、JSON | 仅项目所属范围内可写；保留 SHA 和来源记录 |

`project_id` 在当前 MVP 中用于**查询隔离**，不是账号安全边界。第一版只适用于受控团队环境；对外多用户部署前，必须另行实施身份认证、项目成员关系、角色权限、审计身份与访问控制。不得把“按 project_id 过滤”宣传为“已有完整多租户授权”。

### 3.2 `CanonicalPaper` 与 `SourceDocument` 的分工

```text
CanonicalPaper：作品/论文层身份，一篇论文一个稳定内部 ID
SourceDocument：某个实际获取文件或版本，一个文件一条记录
SourceChunk：某一 SourceDocument 的可定位文本片段
EvidenceQuote：为一次检索或论证选出的可引用摘录
```

建议数据结构：

```text
CanonicalPaper
  canonical_paper_id          # 创建时生成的稳定 UUID/ULID，不由 SHA 推导
  normalized_doi | null
  normalized_title
  year | null
  journal | null
  identity_status             # RESOLVED | POSSIBLE_DUPLICATE | UNRESOLVED
  created_at

SourceDocument
  source_id
  canonical_paper_id | null
  corpus_id
  owner_project_id | null
  source_sha256               # 文件版本、去重与完整性使用
  original_filename
  acquired_from_url | null
  file_version_label | null
  ingestion_status            # 见 3.4
  imported_at

SourceChunk
  chunk_id
  source_id
  canonical_paper_id | null
  chunk_index
  text_sha256
  section_hint | null
  page_start | null
  page_end | null
  char_start
  char_end
  locator_status              # RESOLVED | UNRESOLVED
```

### 3.3 身份解析规则

身份解析必须保守，宁可留下待核验项，也不能错合并两篇论文：

```text
1. 相同 corpus 内 source_sha256 相同：同一 SourceDocument，返回既有记录
2. 规范化 DOI 精确相同：关联既有 CanonicalPaper；可新增 SourceDocument 版本
3. 受控发布清单中的 source_filename 精确相同：按清单关联 CanonicalPaper
4. 标题 + 年份 + 期刊完全规范化一致：标记 POSSIBLE_DUPLICATE，等待人工确认
5. 其他情况：创建新 CanonicalPaper 或标记 UNRESOLVED；绝不做模糊自动合并
```

现有 `paper_id → filename → DOI → title` 映射可作为第一版受控清单，但不能把 DOI 作为唯一主键：当前 122 条记录中 72 条无 DOI。对这批历史语料，首次迁移以受控清单的 `graph_paper_id` 初始化 `CanonicalPaper`；后续新增论文才在创建时分配 UUID/ULID。两种方式都不得由文件 SHA 或模糊标题派生。

### 3.4 用户上传状态机与核验状态机

导入状态和证据可靠性不能共用一个字段：

```text
SourceDocument.ingestion_status
RECEIVED
→ TEXT_EXTRACTED
→ CHUNKED
→ INDEXED
→ SEARCHABLE
↘ FAILED (保留失败原因、不得静默丢失)

EvidenceQuote.verification_status
demo_seed | model_generated_unverified | source_verified | human_verified
```

普通上传默认生成 `model_generated_unverified` 候选。普通 API 不得接受或设置 `human_verified`；该状态只能由未来带登录身份、人工审批记录的审批节点设置。

### 3.5 网络发现与用户补充资料

本系统可以在后续加入 `LiteratureDiscoveryOperator`，但其职责严格限定为“发现候选项”，推荐首批接入 Crossref 与 OpenAlex：

```text
研究问题
→ 网络候选（题名、作者、DOI、摘要链接、来源平台）
→ LiteratureCandidate(candidate_status=DISCOVERED_UNIMPORTED)
→ 用户确认版权/权限并上传合法全文或可使用版本
→ SourceDocument 导入状态机
→ 切片、索引、定位、Evidence 生成与核验
```

网络返回的元数据、搜索摘要、LLM 摘要都不能直接升级为正式 Evidence。首版不自动批量下载全文，即便目标带有开放获取标志，也必须保留获取来源和许可策略后再决定是否自动化。

---

## 4. 可复现资产与就绪闸门

### 4.1 受控 Manifest

大文件保持本地受控并被 Git 忽略；Git 只保存无全文的 manifest、身份映射和派生图资产。每次启动混合检索前读取并验证：

```json
{
  "corpus_id": "physics_stem_v1",
  "corpus_version": "1.0.0",
  "paper_count": 122,
  "vector_chunk_count": 1788,
  "embedding_model": "text-embedding-v3",
  "embedding_dimension": 1024,
  "sparse_index_type": "BM25",
  "sparse_index_version": "1.0.0",
  "graph_artifact": "SparsePaperGraph",
  "graph_paper_count": 122,
  "graph_triple_count": 944,
  "identity_map_sha256": "...",
  "vector_metadata_sha256": "...",
  "faiss_index_sha256": "...",
  "sparse_index_sha256": "...",
  "graph_artifact_sha256": "...",
  "published_at": "...",
  "status": "READY"
}
```

### 4.2 `HybridRetrievalReadinessGate`

以下任一项失败，禁止启用 `hybrid`；必须输出明确降级状态，而不是伪装为混合检索：

```text
身份映射不是 122 条或有重复 canonical_paper_id
FAISS ntotal != vector metadata 数量
查询 embedding 维度 != 1024
向量 metadata 中任一关键记录无法解析到 CanonicalPaper
图资产 paper_count != 122 或 total_triples != 944
任一受控资产 SHA256 与 manifest 不一致
共享语料 PDF / index 路径不可读
```

降级矩阵：

| 组件状态 | 允许结果 | 必须写入 `retrieval_trace` |
|---|---|---|
| vector + sparse + graph 可用 | `HYBRID_GRAPH_GUIDED` | 三路状态、版本、hash、候选说明 |
| graph 不可用 | `HYBRID_DENSE_SPARSE` | `graph_navigation_unavailable` |
| vector 不可用、sparse 可用 | `SPARSE_ONLY` | `vector_retrieval_unavailable` |
| 共享语料不就绪 | 本地 Context MVP 或失败 | 不得产生共享语料检索结论 |

### 4.3 稀疏检索修正

当前 `bm25.pkl` 的真实内容是 TF-IDF 结构而不是 BM25，且 pickle 会受 Python/sklearn 版本影响。实施时：

```text
输入：1788 条 metadata.text
分词：Unicode NFKC + casefold + 中英文分词版本化
模型：BM25Okapi（k1=1.2, b=0.75）
输出：版本化、本地受控、可重建的 sparse index
```

在真 BM25 建好以前，代码和演示统一称它为 `TfidfSparseRetriever`，不得在报告里写“已有 BM25”。

---

## 5. 轻量 GraphRAG 的精确定义与实现

### 5.1 首版 GraphRAG 是什么

首版是以下组合：

```text
论文级 SparsePaperGraph
+ PaperIdentityResolver
+ GraphRetriever（查询 → 相关论文候选 + 关系导航解释）
+ 段落级 Dense/Sparse Retriever
+ 可定位 EvidenceQuote
```

它的职责是从研究主题、教学法、技术、研究方法、学习结果、学生群体等论文级 facet 中，缩小“优先去哪些论文找原文”的范围。它不进行复杂多跳推理，也不自动将三元组改写为研究结论。

### 5.2 首版 GraphRetriever 的输入和输出

输入：规范化后的中英文查询、只读的 `sparse_paper_graph_v2.json`、身份映射。
输出：最多 20 个 `canonical_paper_id` 及可解释的导航痕迹。

```json
{
  "canonical_paper_id": "cp_...",
  "graph_paper_id": "01_AIMS_10.3934_steme.2026023",
  "navigation_score": 0.82,
  "matched_facets": ["generative ai", "physics education", "instructional scaffolding"],
  "supporting_edge_refs": ["graph:01_AIMS...:3"],
  "source_status": "model_generated_unverified"
}
```

固定安全和成本约束：

```text
不调用 LLM
最多 20 篇候选论文
仅论文 → facet 的一跳匹配；首版无跨论文多跳扩展
不连接 Neo4j；直接读取版本化 JSON
不写入图、不修改三元组、不创建 Evidence
```

### 5.3 HybridRetriever 的固定顺序

```text
1. QueryNormalizer：保留原查询和规范化查询；记录语言
2. GraphRetriever：产生最多 20 个候选 CanonicalPaper
3. DenseRetriever：在全语料检索 top 20 段
4. SparseRetriever：在全语料检索 top 20 段
5. 对图候选论文分别取 dense top 40 + sparse top 40 段
6. 合并、按 canonical_chunk_id 去重，每篇论文最多保留 2 个段
7. 只用 dense_rank 与 sparse_rank 进行 RRF
8. Graph 的导航结果仅作为 candidate channel 与 retrieval_trace
9. EvidenceSelector 选择可定位摘录，随后才进入核验过滤
```

RRF 固定为：

```text
RRF(chunk) = 1 / (60 + dense_rank) + 1 / (60 + sparse_rank)
```

`navigation_score` 绝不写入这个公式。图可能没有帮助，甚至可能伤害召回；它必须靠评测结果而不是“看上去很智能”来决定是否默认开启。

### 5.4 证据定位

向量 metadata 现有 `filename / doi / title / section_hint / chunk_index / text` 仍不够用于正式引用。首次构建共享语料时，须用逐页 PDF 文本建立：

```text
CanonicalChunk
  source_page_start / source_page_end
  char_start / char_end
  source_locator_method = PAGE_TEXT_EXACT | NORMALIZED_TEXT_MATCH | UNRESOLVED
```

`UNRESOLVED` chunk 可返回给 DiscoveryContextBundle，但不能被 `FormalEvidenceContextBundle` 选中。

---

## 6. Evidence 与 ContextBundle

### 6.1 两种 ContextBundle

| 字段 | `DiscoveryContextBundle` | `FormalEvidenceContextBundle` |
|---|---|---|
| 用途 | 探索研究范围、发现文献与研究空白 | 研究设计、论文、正式审稿支持 |
| 允许状态 | 四类来源状态均可，但必须明示 | 仅 `source_verified` / `human_verified` |
| 图三元组 | 仅导航轨迹、不可作引文 | 仅导航轨迹、不可作引文 |
| 未定位 chunk | 可显示并标记限制 | 拒绝纳入 |
| 证据不足 | 返回风险和候选补充方向 | `BLOCKED_FOR_FORMAL_USE` |

### 6.2 `EvidenceQuote`

正式上下文的最小证据单元不是一篇论文也不是一个三元组，而是可反查的原文摘录：

```text
evidence_id
corpus_id
source_id
canonical_paper_id
canonical_chunk_id
quote_text
quote_sha256
quote_char_start / quote_char_end
source_page_start / source_page_end
retrieval_modalities              # dense / sparse / graph_navigation
verification_status
verified_by | null
verified_at | null
verification_note | null
```

任何论文中的 AtomicClaim 均应保持：

```text
AtomicClaim
→ ClaimEvidenceMap
→ EvidenceQuote
→ CanonicalChunk
→ SourceDocument + SHA256
→ 原始 PDF 页码/字符位置
```

### 6.3 Bundle 指纹

`context_hash` 必须由输入、检索配置和最终引用共同决定：

```text
project_id + task_ref + normalized query + context_mode
+ corpus/version + manifest hashes + identity-map version
+ retrieval configuration + ordered quote_id/quote_sha256/status
```

相同输入、同一资产版本、同一策略应产生相同 `context_hash`。资料、核验状态、索引或选择顺序任一改变，都必须产生新的 hash。

---

## 7. 系统模块边界：后端、Controller 与 LangGraph

### 7.1 新增模块建议

```text
backend/src/stem_sci/knowledge/
  models.py                 # Corpus、CanonicalPaper、检索 DTO
  identity.py               # PaperIdentityResolver
  manifest.py               # 受控资产完整性校验
  corpus_store.py           # 共享/项目私有语料访问策略
  sparse_retriever.py       # 真 BM25 或明确命名的 TF-IDF 实现
  vector_retriever.py       # FAISS + 查询 embedding 适配器
  graph_retriever.py        # 只读 SparsePaperGraph 导航
  hybrid_retriever.py       # 两阶段候选与 RRF
  evidence_selector.py      # 段落到 EvidenceQuote
  assembler.py              # 两种 ContextBundle
  readiness_gate.py         # HybridRetrievalReadinessGate
  discovery.py              # 后续 LiteratureCandidate，不下载全文
```

职责不重叠：

```text
context/    = 工件持久化、既有导入/证据/ContextBundle 协议兼容
knowledge/  = 语料读取、身份解析、检索、定位、检索轨迹
graph_rag/  = 离线构图工具；不是生产后端 import 依赖
agents/     = 消费 ContextBundle，生成候选科研工件
controller/ = 路由、闸门、审计、唯一的 current_stage 修改权
```

### 7.2 LangGraph 的位置

LangGraph 当前**没有实施**，也不应为本次混合检索上线制造前置阻塞。此版本只提供可由 Controller 调用的 `HybridContextProvider`：

```text
ResearchController
  → ContextProvider protocol
      → LocalContextProvider（当前默认/降级）
      → HybridContextProvider（本计划交付）
```

以后接入 LangGraph 时，只能由 `LangGraphWorkflowAdapter` 调用 Controller 已批准的动作。规则不变：

```text
LangGraph node、Agent、Retriever、Reviewer：无权修改 current_stage
ResearchController：唯一可根据 GateResult / RouteDecision 修改 current_stage
```

也就是说，LangGraph 是未来的流程编排实现选择，不是研究状态权力来源，更不是 GraphRAG 的同义词。

---

## 8. API 与前端最小变更

保留当前 Source/Evidence/Context API，新增或扩展：

```text
GET  /api/v1/corpora
GET  /api/v1/corpora/{corpus_id}/manifest
POST /api/v1/retrieval/search
POST /api/v1/context/build               # 新增 context_mode、corpus_ids、strategy
GET  /api/v1/context/{context_id}
```

`POST /api/v1/retrieval/search` 最小响应必须有：

```text
retrieval_status
degraded_mode | null
candidate_papers
chunk_hits
retrieval_trace
risk_flags
manifest_refs
```

前端必须区分：

```text
语料：项目资料 / Physics-STEM 共享语料
用途：探索 / 正式证据
来源标签：Dense / Sparse / Graph navigation
可信状态：demo_seed / unverified / source_verified / human_verified
定位：PDF 页码、段落、来源文件
```

前端不得把 `model_generated_unverified` 用绿色“已验证”样式呈现，也不得隐藏检索降级状态。

---

## 9. 实施顺序、测试与验收

### 9.1 工作包 A：身份、定位和资产闸门

交付：`CanonicalPaper`、`SourceDocument` 版本关系、受控 manifest、122 篇身份导入器、1788 chunk 定位器。

验收：

```text
122 篇均解析到一个 CanonicalPaper 或明确 UNRESOLVED
同 SHA 不重复导入；同 DOI 的不同文件版本不误建两篇论文
不因标题相似自动合并
FAISS = metadata = 1788；维度 = 1024
图资产 = 122 paper / 944 triples；hash 与 manifest 一致
每个 Formal 候选 chunk 均有页码或等价精确定位
```

### 9.2 工作包 B：三种检索器和混合链

交付：真 BM25、DenseRetriever、GraphRetriever、HybridRetriever 和明确降级状态。

验收：

```text
图分数不参与 RRF
图不可用时仍可 Dense + Sparse 检索
向量不可用时明确为 SPARSE_ONLY
每篇论文最终最多 2 个 chunk
相同查询和索引版本的排序可复现
任何 API key、绝对本地路径、完整 PDF 均不出现在响应中
```

### 9.3 工作包 C：Evidence 与 ContextBundle

交付：`EvidenceQuote`、双模式 ContextBundle、`HybridContextProvider`、现有 Context MVP 向后兼容。

验收：

```text
Formal 模式 0 条 unverified Evidence
Discovery 模式可展示未核验资料，但显式显示状态
每一条已选 Evidence 均可反查到 PDF
普通 API 传 human_verified 被拒绝
context_hash 对任何资产/状态/策略变化敏感
```

### 9.4 工作包 D：评测和默认开关决策

建立至少 20 个中英文查询的版本化 Gold Set，双人独立标注相关论文、强相关段落和可接受摘录；分歧由第三人或负责人裁决。

比较五种策略：

```text
SQLite keyword baseline
Sparse only
Dense only
Dense + Sparse RRF
Graph-guided Dense + Sparse RRF
```

硬验收：

```text
20/20 查询均有结构化 retrieval_trace
ContextBundle 可追溯率 = 100%
跨项目私有资料泄露 = 0
FormalBundle 含未核验 Evidence = 0
资产 hash 不匹配时错误放行 = 0
```

只有 Graph-guided 版本在冻结 Gold Set 上不低于 Dense+Sparse 的 Chunk Hit Rate@5，且至少对 1 个问题有清晰可复核的增益，才可默认启用图导航；否则保留为可选探索功能。

### 9.5 必需自动化测试

```text
test_identity_same_sha_returns_same_source
test_identity_same_doi_creates_new_file_version_not_new_canonical_paper
test_identity_title_similarity_is_not_auto_merge
test_manifest_mismatch_blocks_hybrid
test_graph_results_do_not_change_rrf_score
test_graph_failure_degrades_to_dense_sparse
test_vector_failure_is_marked_sparse_only
test_formal_bundle_rejects_unverified_and_unresolved_locator
test_evidence_quote_round_trips_to_source_chunk_and_locator
test_project_private_corpus_isolated
test_shared_corpus_is_read_only
test_regular_api_rejects_human_verified
test_context_hash_changes_with_manifest_or_evidence_status
```

CI 仅使用合成小语料、假 Vector/Graph 适配器；真实 122 篇、FAISS、PDF 与网络 embedding 调用只在本地受控验收运行。

---

## 10. 提交拆分与团队分工

```text
1. feat(knowledge): add canonical identity, corpus manifests and readiness gate
2. feat(retrieval): add reproducible dense sparse graph-guided retrieval
3. feat(context): add evidence quotes and formal discovery context bundles
4. test(evaluation): add physics stem retrieval benchmark and report
```

| 角色 | 负责内容 | 不负责内容 |
|---|---|---|
| 资料/核验成员 | 题录、来源、许可说明、20 题 Gold Set、关键摘录核验 | 修改索引算法或改变验证状态规则 |
| 后端成员 | identity、manifest、retriever、API、迁移、测试 | 更改 Controller 阶段权力或从网络批量下载论文 |
| 图谱成员 | 图资产质量、schema、导航 facet、图解释 | 把三元组直接升级为正式证据 |
| 前端成员 | 语料/模式选择、来源标签、证据反查、降级展示 | 直接访问本地 FAISS/PDF 或保存密钥 |
| 评测成员 | Gold Set、指标、盲测、报告 | 为了展示效果修改冻结答案集 |

---

## 11. 明确延后事项

```text
Microsoft GraphRAG community detection / global search / community reports
Neo4j 生产部署与远程图数据库运维
对全部 1788 个 chunk 再调用 LLM 做细粒度三元组抽取
LLM reranker、自动 query rewrite、自动研究结论写作
ConversationStore、ShortMemory、LongMemory
用户账户、完整 RBAC、跨组织协作权限
自动批量下载或发布受版权限制的 PDF
LangGraph StateGraph 工作流与真实多 Agent 执行编排
```

这些不是“不重要”，而是必须在混合检索、证据追溯和验收稳定后再接入。尤其不能以“GraphRAG”名义提前绕过来源核验、定位和人工批准。

---

## 12. 实施前仍须负责人确认的事项

以下事项不能由实现者自行决定：

1. `physics_stem_v1` 的 122 篇 PDF 是否在团队私有仓库、演示机和竞赛展示中均有合法保留/展示权限；Git 仅存派生资产和 manifest 不能替代版权确认。
2. Discovery 的首批网络来源是否锁定为 Crossref + OpenAlex；是否允许随后引入 Semantic Scholar 或期刊站点适配器。
3. 共享语料是否允许把已经 `source_verified` 的摘录状态复用于多个项目，还是每个项目必须重新核验。
4. 当前 DashScope 查询 embedding 是否可继续用于竞赛演示；若后续迁移本地 embedding，必须创建新向量索引，绝不能把不同维度向量写入同一索引/Collection。
5. 是否接受“未实现认证前，只部署在内部团队环境”的限制；若要让外部用户注册上传，认证/RBAC 是阻塞项。
6. `UNRESOLVED_LOCATOR` 的历史 chunk 是否应先全部补页码，再允许 `physics_stem_v1` 的 Formal 模式上线。

在以上问题没有负责人决定前，可以实现只读解析、合成测试和 Discovery 模式；但不应宣称共享语料已经能支撑正式科研结论。

---

## 13. 完成定义

本计划完成的标志不是页面上出现“GraphRAG”按钮，而是以下链路真实可复现：

```text
中英文 Physics-STEM 问题
→ 图谱给出论文候选与可解释导航
→ Dense + Sparse 检索定位真实原文段落
→ 身份解析关联同一论文及文件版本
→ EvidenceQuote 反查 PDF 页码/文本位置
→ 人工核验关键摘录
→ FormalEvidenceContextBundle
→ Controller 交给 Evidence / Writing Agent
→ 每个正式 AtomicClaim 都可反向追溯
```

届时可准确表述为：

> STEM-SCI 已实现面向 Physics-STEM 教育研究的、图导航增强的混合检索与证据上下文链：论文级稀疏关系图负责发现关联研究，段落级检索负责定位原文，正式 ContextBundle 只纳入可定位、可核验的 Evidence；图谱三元组用于导航而不替代科研证据。
