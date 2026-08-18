# STEM-SCI 上下文与存储架构总览

> 先看本文了解模块分工；需要字段和约束时，再阅读同目录下的 CONTEXT_MEMORY_STORAGE_DESIGN.md。

## 1. 一句话理解

STEM-SCI 不是一个把所有内容混在一起的聊天框，而是六个模块组成的科研工作平台：

    对话
    → 检索
    → 上下文
    → Agent
    → 工件与审批
    → 记忆

## 2. 六个模块的职责

| 模块 | 负责什么 | 不负责什么 | 输出 |
|---|---|---|---|
| 对话模块 | 保存用户和系统的交互历史 | 不判断科研结论，不改变研究阶段 | Conversation、Message |
| 资料模块 | 保存 PDF、切片、来源位置和 Evidence | 不回答问题，不批准结论 | SourceDocument、SourceChunk、Evidence |
| 检索模块 | 用 BM25、向量库、论文图寻找候选资料 | 不批准证据，不直接写论文 | RetrievalResult |
| 上下文模块 | 去重、排序、核验、token裁剪，组成证据包 | 不保存完整文件，不替代工件 | ContextBundle |
| 记忆模块 | 保存当前任务和项目级摘要 | 不替代原文证据和审批记录 | ShortMemory、LongMemory |
| 工件模块 | 保存协议、代码、结果、论文和审批 | 不负责普通检索和聊天显示 | Artifact、Decision、ExecutionRun |

最容易混淆的四个概念：

- Message：用户和系统说了什么；
- ContextBundle：当前任务需要参考什么；
- Memory：以后可以复用什么；
- Artifact：平台正式生成了什么。

## 3. 一张完整流程图

    用户提问
       ↓
    对话模块保存 Message
       ↓
    检索模块
       ├── BM25关键词检索
       ├── 向量语义检索
       └── 论文关系图扩展候选论文
       ↓
    RRF融合、去重、排序
       ↓
    上下文模块生成 ContextBundle
       ↓
    Agent读取 ContextBundle
       ↓
    生成候选 Artifact
       ↓
    Gate / Reviewer / Human Approval
       ↓
    ArtifactStore 保存正式版本
       ↓
    ShortMemory / LongMemory 保存可复用摘要

## 4. 当前已经有什么

| 能力 | 位置 | 状态 |
|---|---|---|
| PDF导入和原文保存 | .stem_sci/uploads/ | 已实现 |
| 文本切片、Evidence、ContextBundle | .stem_sci/context.db | 已实现基础版 |
| BM25和FAISS向量检索 | data/local/vector_kb/vectordb/ | 已生成，尚未接入ContextService |
| 论文级稀疏关系图 | data/local/profile_batch_all_v2.json | 已生成，122篇、944条三元组 |
| 对话持久化 | Conversation/Message表 | 尚未实现 |
| ShortMemory | MemoryService | 尚未实现 |
| LongMemory | 长期记忆审批链 | 尚未实现 |
| ArtifactStore | 版本化科研工件 | 目前主要是接口和模型 |
| DecisionStore | Gate和人工审批记录 | 目前主要是接口和模型 |

所以当前是：

    Context MVP
    + 独立向量库
    + 独立论文关系图

还不是完整的“对话—上下文—工件—记忆”闭环。

## 5. 数据分别保存在哪里

### 5.1 对话

未来由 ConversationStore 保存：

    Conversation
      conversation_id
      project_id
      user_id
      title
      current_task_ref
      created_at
      updated_at

    Message
      message_id
      conversation_id
      project_id
      sequence
      role
      content
      context_bundle_ref
      artifact_refs
      created_at

对话内容只用于恢复用户工作历史，不能自动成为正式科研证据。

### 5.2 知识库

当前：

    .stem_sci/
    ├── context.db
    └── uploads/
        └── <project_id>/
            └── <sha256>.<extension>

其中保存来源资料、切片、Evidence 和 ContextBundle。

### 5.3 向量库和论文图

    data/local/vector_kb/vectordb/
    ├── index.faiss
    ├── bm25.pkl
    └── metadata.json

    data/local/profile_batch_all_v2.json

向量库负责找相关切片，论文图负责找相关论文。二者都不能直接替代来源核验。

### 5.4 科研工件

未来由 ArtifactStore 保存：

    ArtifactStore/
    └── <project_id>/
        ├── paper_cards/
        ├── study_protocols/
        ├── analysis_plans/
        ├── code_artifacts/
        ├── statistical_results/
        ├── paper_drafts/
        └── reviews/

审批记录由 DecisionStore 单独保存。执行代码、日志、SPSS/Python输出由 ExecutionStore 保存。

## 6. Context 和 Memory 的区别

### ContextBundle

回答：

    当前任务需要看哪些证据？

包含：

    query
    evidence_refs
    paper_refs
    memory_refs
    verification_summary
    token_budget
    unresolved_questions
    context_hash

它必须能反查：

    ContextBundle
    → EvidenceRef
    → SourceChunk
    → SourceDocument
    → 原始PDF

### ShortMemory

回答：

    当前任务进行到哪里？

保存当前问题、最近 ContextBundle、已选证据和未解决问题。

### LongMemory

回答：

    这个项目以后可以复用什么？

保存经过整理的摘要、来源引用和工件引用。Agent 可以提出候选记忆，但不能自行设置 human_verified。

## 7. GraphRAG 的正确位置

当前论文关系图是论文级 Profile Graph：

    论文 → 方法
    论文 → 教学法
    论文 → 技术
    论文 → 领域
    论文 → 学习结果
    论文 → 样本
    论文 → 主张

它负责导航和候选扩展，不负责直接提供可发表结论。

推荐：

    论文关系图找到候选论文
    → 向量库找到具体切片
    → ContextBundle打包证据

不建议默认对每一个切片都调用一次模型抽取三元组。

## 8. ResearchState 的边界

ResearchState 只保存引用：

    conversation_ref
    current_task_ref
    context_bundle_refs
    artifact_refs
    execution_run_refs
    decision_refs
    short_memory_summary
    long_memory_refs

它不保存完整 PDF、向量矩阵、完整代码、原始统计输出或大段聊天历史。

## 9. 推荐实施顺序

### 第一步：接通已有资料

    Context MVP
    + BM25
    + FAISS
    + 论文关系图
    → HybridRetriever
    → ContextBundle

### 第二步：保存对话

实现 ConversationService 和 MessageStore，让刷新页面后仍能恢复对话。

### 第三步：加入 ShortMemory

只保存当前任务所需的摘要和引用。

### 第四步：保存科研工件

实现 ArtifactMetadataStore 和 FileArtifactStore，支持版本、SHA256、来源引用和状态。

### 第五步：加入 LongMemory 和审批

长期记忆只能使用经过规则、Reviewer 或人工批准的内容。

## 10. 必须遵守的边界

1. 对话不等于证据。
2. 检索结果不等于正式结论。
3. 论文关系图不等于原文证据。
4. Memory 不替代 Evidence 或 Decision。
5. ContextBundle 不保存完整文件。
6. ArtifactStore 不决定工件是否通过。
7. Agent 不改变 current_stage。
8. 所有数据按 project_id 隔离。
9. 正式数字必须反查 ExecutionRun。
10. model_generated_unverified 不能直接支撑正式论文结论。
