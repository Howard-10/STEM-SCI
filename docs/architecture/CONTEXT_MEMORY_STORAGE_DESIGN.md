# STEM-SCI 上下文、对话、记忆与工件存储详细设计

> 文档状态：设计稿
> 本文只整理架构边界，不代表所有目标模块已经实现。
>
> 第一次阅读请先看 [CONTEXT_MEMORY_STORAGE_OVERVIEW.md](./CONTEXT_MEMORY_STORAGE_OVERVIEW.md)，本文作为字段、约束和实施细节附录。

## 0. 一句话结论

STEM-SCI 不应把所有内容都放进聊天记录或一个数据库，而应采用：

    对话存储
    + 原始资料与切片存储
    + BM25/向量检索
    + 论文关系图
    + ContextBundle
    + ShortMemory / LongMemory
    + ArtifactStore / DecisionStore / ExecutionStore

每一层保存不同对象，通过 ID 和引用连接起来。

## 1. 先看当前实际情况

| 模块 | 当前实际位置 | 当前能力 | 当前限制 |
|---|---|---|---|
| 原始资料、切片、Evidence | .stem_sci/context.db 和 .stem_sci/uploads/ | PDF 导入、SHA256 去重、切片、Evidence 反查 | 仍是确定性关键词检索 |
| 向量知识库 | data/local/vector_kb/vectordb/ | FAISS + BM25 + RRF | 尚未接入 ContextService |
| 论文关系图 | data/local/profile_batch_all_v2.json、graph_rag/ | 122 篇论文、944 条论文级三元组 | 尚未接入 ContextService |
| ContextBundle | context.db 的 bundles 表 | 可构建、裁剪、保存、反查 | 还没有图检索和向量检索结果 |
| 对话 | 当前没有 Conversation/Message 持久化 | 前端可暂时输入和操作 | 刷新页面后对话状态会丢失 |
| ShortMemory | 只有模型/引用设计 | 尚未形成独立服务 | 不能跨任务复用 |
| LongMemory | 尚未实现 | 只有 MemoryRef 设计 | 不能作为正式知识来源 |
| 科研工件 | Phase 1 主要是接口和模型 | 规划了 ArtifactStore | 尚未形成完整生产存储链 |

因此，当前不能说“对话、记忆和科研工件已经全部落库”，现在真正落地的是 Context MVP 和独立的向量/论文图资产。

## 2. 目标架构总览

    用户
      ↓
    ConversationStore
      ↓
    Task / Controller
      ↓
    ContextProvider
      ├── SourceEvidenceStore
      ├── BM25Retriever
      ├── VectorRetriever
      ├── PaperGraphRetriever
      └── MemoryManager
      ↓
    ContextBundle
      ↓
    Agent / Reviewer
      ↓
    ArtifactStore
      ├── DecisionStore
      └── ExecutionStore

其中：

- ConversationStore 保存用户和系统消息；
- SourceEvidenceStore 保存原始资料、切片和证据；
- BM25/Vector/PaperGraph 负责不同类型的检索；
- MemoryManager 提供任务连续性；
- ContextBundle 是交给任务或 Agent 的统一上下文入口；
- ArtifactStore 保存平台生成的正式工件；
- DecisionStore 保存 Gate、Reviewer 和人工审批决定；
- ExecutionStore 保存代码、日志和统计软件输出。

## 3. 四类数据分别存什么

### 3.1 对话数据

对话是用户界面历史，不是科研证据。

保存：

- 用户输入；
- 系统回答；
- 当前任务引用；
- 使用过的 ContextBundle；
- 生成过的工件引用；
- Agent 运行引用。

不保存为正式证据：

- 未核验的聊天结论；
- Agent 自己生成的“事实”；
- 未经审批的研究设计；
- 未经执行验证的统计数字。

### 3.2 知识库数据

知识库保存用户上传和处理后的资料：

- 原始 PDF/Markdown/TXT/JSON；
- 文本切片；
- 来源位置；
- Evidence；
- PaperCard；
- 向量索引；
- BM25 索引；
- 论文级关系图。

### 3.3 平台生成的科研工件

平台生成的内容应保存为版本化工件：

- PaperCard；
- EvidenceMatrix；
- StudyProtocol；
- PreregisteredAnalysisPlan；
- ExecutableAnalysisPlan；
- CodeSpecification；
- CodeArtifact；
- ResultValidationReport；
- StatisticalResultCard；
- PaperDraft；
- ReviewReport。

这些内容不能只留在 Message.content 中。

### 3.4 记忆数据

Memory 保存任务摘要和可复用线索：

- 当前任务的短期上下文；
- 已确认的项目术语；
- 已选用的证据引用；
- 已批准工件的摘要；
- 尚未解决的问题。

Memory 不保存整篇 PDF、完整代码、完整数据集或完整执行日志。

## 4. 存储层设计

| 存储层 | 保存对象 | MVP 技术 | 后续可替换技术 |
|---|---|---|---|
| ConversationStore | Conversation、Message | SQLite | PostgreSQL |
| SourceEvidenceStore | SourceDocument、SourceChunk、Evidence | SQLite + 本地文件 | PostgreSQL + 对象存储 |
| VectorStore | Embedding 和索引元数据 | FAISS | PGVector/独立向量服务 |
| KeywordStore | BM25 倒排索引 | BM25 文件 | PostgreSQL FTS |
| PaperGraphStore | 论文、实体、关系边 | JSON/Neo4j Adapter | Neo4j/图数据库 |
| MemoryStore | ShortMemory、LongMemory | SQLite | PostgreSQL/专用记忆库 |
| ArtifactStore | 版本化科研工件 | 本地目录 | 对象存储 |
| DecisionStore | Gate/Reviewer/人工决定 | SQLite | PostgreSQL |
| ExecutionStore | 代码、日志、SPSS/Python 输出 | 本地 Run 目录 | 对象存储 |

不要求 MVP 一开始就搭建 PostgreSQL、PGVector、Neo4j 和对象存储。关键是先保持接口和数据边界正确。

## 5. 当前本地目录和目标目录

### 5.1 当前 Context MVP

    .stem_sci/
    ├── context.db
    └── uploads/
        └── <project_id>/
            └── <sha256>.<extension>

### 5.2 当前向量库和关系图

    data/local/vector_kb/vectordb/
    ├── index.faiss
    ├── bm25.pkl
    └── metadata.json

    data/local/profile_batch_all_v2.json

这些属于本地实验数据和索引，不应直接提交到 Git。

### 5.3 未来平台存储

    storage/
    └── <project_id>/
        ├── raw/
        ├── chunks/
        ├── memory/
        ├── artifacts/
        ├── decisions/
        └── executions/

实际工程中可以继续使用 .stem_sci/ 作为默认本地目录，但目录职责必须保持上述边界。

## 6. 对话如何持久化

### 6.1 Conversation

    conversation_id
    project_id
    user_id
    title
    status
    current_task_ref
    created_at
    updated_at

### 6.2 Message

    message_id
    conversation_id
    project_id
    sequence
    role                 # user / assistant / system
    content
    created_at
    context_bundle_ref
    artifact_refs
    agent_run_ref
    token_usage

消息的作用是恢复界面和任务历史。它不能直接改变 current_stage，也不能绕过 Controller、Gate 或 Human Approval。

### 6.3 一次回答的引用链

    Message
      ├── context_bundle_ref
      ├── evidence_refs
      ├── artifact_refs
      └── agent_run_ref

这样用户可以从一条回答继续查看：

    回答
    → ContextBundle
    → EvidenceRef
    → SourceChunk
    → SourceDocument
    → 原始 PDF

## 7. 切片、向量和论文关系图如何协作

### 7.1 切片和向量检索

向量检索回答：

> 哪些正文片段与问题语义相关？

每个切片至少需要：

    project_id
    source_id
    paper_id
    chunk_id
    chunk_index
    page_start
    page_end
    section
    text
    char_start
    char_end
    content_sha256
    embedding_model
    embedding_dimension

### 7.2 论文级关系图

当前 profile graph 回答：

> 哪些论文在主题、方法、技术或学习结果上相关？

它应该用于：

- 查询扩展；
- 候选论文发现；
- 相关论文导航；
- 缩小向量检索范围。

它不能直接替代正文 Evidence。

### 7.3 推荐检索流程

    用户问题
      ↓
    项目和来源状态过滤
      ↓
    三路召回
      ├── BM25 精确检索
      ├── 向量语义检索
      └── 论文关系图候选扩展
      ↓
    RRF 融合
      ↓
    同源去重和多样性控制
      ↓
    可选 Reranker
      ↓
    反查 SourceChunk
      ↓
    ContextBundle

不建议默认对每个切片调用一次 LLM 抽取三元组。推荐先用论文级关系图找论文，再用向量库找证据片段，只有在需要深度审核时才抽取证据级关系。

## 8. ContextBundle 的职责

ContextBundle 是“当前任务需要的证据包”，不是完整知识库，也不是聊天记录备份。

建议字段：

    context_id
    project_id
    task_ref
    query
    evidence_refs
    paper_refs
    memory_refs
    retrieval_trace
    verification_summary
    unresolved_questions
    risk_flags
    token_budget
    estimated_tokens
    context_hash
    generated_at

ContextBundle 必须：

- 遵守 project_id 隔离；
- 遵守允许的 verification_status；
- 保留 Evidence → SourceChunk 的关系；
- 遵守 token_budget；
- 限制同一来源重复切片；
- 不保存完整 PDF、向量矩阵或二进制文件。

正式论文结论只允许依赖 source_verified 或 human_verified 内容。demo_seed 和 model_generated_unverified 只能作为候选或演示材料。

## 9. 对话、ShortMemory 和 LongMemory 的区别

| 对象 | 作用 | 生命周期 | 是否是正式证据 |
|---|---|---|---|
| Message | 保存用户和系统交互 | 长期保存 | 否 |
| ShortMemory | 保存当前任务上下文 | 当前任务/会话 | 否 |
| LongMemory | 保存项目级可复用摘要 | 跨任务 | 否，除非引用正式证据 |
| EvidenceRef | 指向原文证据 | 随来源保存 | 是候选证据 |
| DecisionRecord | 保存审批决定 | 长期保存 | 是流程记录 |
| ArtifactRef | 指向版本化科研工件 | 长期保存 | 取决于工件状态 |

### 9.1 ShortMemory

ShortMemory 保存：

    当前研究问题
    当前用户目标
    最近使用的 ContextBundle
    已选 EvidenceRef
    未解决问题
    最近检索条件
    当前 context_hash

它可以随着任务推进更新，但不能覆盖正式证据或审批记录。

### 9.2 LongMemory

LongMemory 保存：

    memory_id
    project_id
    memory_type
    summary
    source_refs
    artifact_refs
    verification_status
    created_by
    created_at
    approval_ref

Agent 可以提出 MemoryCandidate，但不能自行把内容标记为 human_verified。

## 10. 科研工件如何保存

### 10.1 ArtifactStore

    ArtifactStore/
    └── <project_id>/
        ├── paper_cards/
        ├── evidence_matrices/
        ├── study_protocols/
        ├── analysis_plans/
        ├── code_artifacts/
        ├── statistical_results/
        ├── paper_drafts/
        └── reviews/

每个工件必须带：

    artifact_id
    artifact_type
    project_id
    version
    status
    sha256
    created_by
    created_at
    input_artifact_refs
    source_refs
    verification_status
    file_path

旧版本不直接覆盖，使用新版本或 superseded_by 关系。

### 10.2 DecisionStore

    decision_id
    project_id
    artifact_id
    gate_name
    decision
    decided_by
    decided_at
    reason

ArtifactStore 记录“生成了什么”，DecisionStore 记录“是否允许继续”。

### 10.3 ExecutionStore

    ExecutionStore/
    └── <project_id>/
        └── <execution_run_id>/
            ├── input_manifest.json
            ├── code/
            ├── logs/
            ├── spss_output/
            ├── python_output/
            └── environment.json

StatisticalResultCard 只能引用这些执行产物，不能脱离 ExecutionRun 单独保存正式数字。

## 11. ResearchState 只保存引用

LangGraph 的 ResearchState 保存轻量状态和引用：

    current_stage
    task_status
    conversation_ref
    current_task_ref
    context_bundle_refs
    artifact_refs
    execution_run_refs
    decision_refs
    short_memory_summary
    long_memory_refs
    risk_flags
    error_log

ResearchState 不保存：

- 完整 PDF；
- 全部正文切片；
- 向量矩阵；
- 完整代码包；
- SPSS/Python 原始输出；
- 大段完整聊天历史。

## 12. 最小实现顺序

### Phase A：统一标识

统一：

    project_id
    source_id
    paper_id
    chunk_id
    artifact_id
    verification_status
    source_sha256

建立 vector index → SourceChunk、graph edge → PaperCard/SourceChunk 的映射。

### Phase B：接入现有混合检索

通过适配器接入现有 FAISS 和 BM25：

    ContextService
      → HybridRetriever
          ├── BM25Adapter
          └── VectorAdapter

不要把 FAISS 逻辑直接写进 ContextService。

### Phase C：接入论文关系图

通过 GraphRetrieverAdapter 使用 profile graph 返回候选 paper_id，再让向量检索定位具体切片。

### Phase D：统一 ContextAssembler

实现：

    召回
    → RRF 融合
    → 去重
    → 核验状态排序
    → token 预算裁剪
    → SourceChunk 反查
    → ContextBundle 生成

### Phase E：增加对话和记忆

优先实现：

1. ConversationService；
2. MessageStore；
3. ShortMemory；
4. ArtifactMetadataStore；
5. FileArtifactStore。

长期记忆审批和自动沉淀放到后续阶段。

## 13. 必须遵守的硬约束

1. 不默认对每个切片调用一次 LLM 抽取三元组。
2. 不把论文级关系图直接当作原文证据。
3. 不混用不同 Embedding 模型或不同向量维度。
4. 不把完整 PDF、向量和大文件写进 ContextBundle 或 Checkpoint。
5. 不让 Memory 覆盖 Evidence 或 Decision。
6. 不让 Agent 直接批准 Artifact、Decision 或 human_verified。
7. 所有查询、对话、记忆和工件按 project_id 隔离。
8. 正式科研数字必须能反查到 ExecutionRun 和输入数据版本。
9. 正式论文主张必须有可核验的 EvidenceRef。
10. 原始 PDF、向量索引、运行日志和本地数据库不直接提交 Git。

## 14. 仍需负责人确认的事项

1. Embedding 使用本地模型，还是继续使用 DashScope；如果切换，是否接受重建全部向量索引。
2. MVP 阶段继续使用 SQLite + FAISS + BM25，还是提前采用 PostgreSQL/PGVector。
3. 论文关系图是否先作为候选检索器，而不是直接参与最终证据排序。
4. Conversation 是否需要用户登录、权限和多人协作。
5. LongMemory 是否必须经过人工审批后才能跨任务使用。
6. ArtifactStore 的生产介质是本地目录、NAS，还是对象存储。

## 15. 最终目标链路

    用户对话
    → 任务和查询
    → 论文关系图导航
    → BM25 + 向量混合检索
    → RRF / 去重 / 重排
    → ContextBundle
    → Agent 候选输出
    → Gate / Reviewer / Human Approval
    → ArtifactStore 版本化工件
    → DecisionStore 审批记录
    → ShortMemory / LongMemory 引用

这套设计的目标不是普通聊天机器人，而是把“用户问题、原文证据、论文关系、上下文、科研工件和审批记录”连接起来的可追溯科研工作平台。
