# STEM-SCI 上下文与知识库实施说明

> 技术线：上下文（知识库）
> 目标：为 Agent、Controller 和科研工作流提供可信、可裁剪、可引用、可追溯的上下文。
> 当前阶段：Phase 1 先完成数据模型、接口和不变量；后续阶段再实现真实 GraphRAG、文献解析和长期记忆。
> 核心原则：上下文负责“提供什么信息”，不负责“决定下一步”，也不负责“执行工具”。

---

## 1. 最终要解决的问题

1. 当前任务真正需要哪些上下文。
2. 信息来自文献、人工决定、协议、工件还是历史记忆。
3. 信息是否已经核验，是否可以进入正式研究结论。
4. 如何避免把全部聊天、整篇 PDF 和完整数据直接塞给 Agent。
5. 如何让每条上下文都能反查原始来源。
6. 如何避免 Memory 替代正式 DecisionStore。
7. 如何在 Token 预算下保留最重要的信息。

## 2. 负责范围

### 2.1 负责

- `PaperCard`、`EvidenceItem`、`SourceLocation`、`EvidenceMatrix`。
- 来源核验状态与证据关系。
- `ShortMemory`、`LongMemory`、`MemoryRef`。
- `ContextBundle`、`ContextProvider`。
- `SourceEvidenceStore` 接口。
- GraphRAG 检索接口、上下文裁剪、去重、排序和引用。
- Agent 输入上下文的版本、来源和哈希。

### 2.2 不负责

- 不修改 `current_stage`。
- 不决定调用哪个 Agent。
- 不执行文献搜索、Python、SPSS 或学生代码。
- 不批准研究问题、研究设计或分析计划。
- 不将模型生成内容直接标记为 `human_verified`。

## 3. 与其他技术线的接口

```text
SourceEvidenceStore / Memory / Project Context
                    ↓
              ContextProvider
                    ↓
              ContextBundle
                    ↓
                Multi-Agent
                    ↓
                AgentResult
                    ↓
                Workflow
```

- 多 Agent 组只通过 `ContextBundle` 获取上下文。
- 工作流组决定何时请求上下文。
- 工具组执行真实检索、文件读取和索引。

## 4. 核心数据对象

### 4.1 EvidenceStatus

```python
class EvidenceStatus(str, Enum):
    DEMO_SEED = "demo_seed"
    MODEL_GENERATED_UNVERIFIED = "model_generated_unverified"
    SOURCE_VERIFIED = "source_verified"
    HUMAN_VERIFIED = "human_verified"
```

规则：

- Agent 不能直接产生 `HUMAN_VERIFIED`。
- 正式文献主张至少需要 `SOURCE_VERIFIED`。
- `MODEL_GENERATED_UNVERIFIED` 只能作为候选材料。
- `DEMO_SEED` 只能用于演示。

### 4.2 SourceLocation

```python
class SourceLocation(BaseModel):
    source_id: str
    page: int | None
    section: str | None
    paragraph: int | None
    line_start: int | None
    line_end: int | None
    quote_hash: str | None
```

### 4.3 EvidenceRef

```python
class EvidenceRef(BaseModel):
    evidence_id: str
    source_id: str
    source_location_ref: str
    verification_status: EvidenceStatus
    claim_supported: str | None
    relation: str
    version: int
```

`relation` 至少支持：

```text
SUPPORTING
CONTRASTING
MENTIONING
```

### 4.4 PaperCard

```python
class PaperCard(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    source_uri: str
    source_hash: str
    research_context: str | None
    sample: str | None
    study_design: str | None
    intervention: str | None
    comparison: str | None
    outcomes: list[str]
    methods: list[str]
    result_refs: list[str]
    limitation_refs: list[str]
    source_location_refs: list[str]
    verification_status: EvidenceStatus
```

### 4.5 MemoryRef

```python
class MemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    summary: str
    source_refs: list[str]
    created_at: datetime
    expires_at: datetime | None
    version: int
```

建议类型：

```text
SHORT_TERM
LONG_TERM
PROJECT_SUMMARY
USER_PREFERENCE
OPEN_QUESTION
```

### 4.6 ContextBundle

```python
class ContextBundle(BaseModel):
    context_id: str
    task_ref: str
    protocol_refs: list[str]
    evidence_refs: list[str]
    decision_refs: list[str]
    artifact_refs: list[str]
    memory_refs: list[str]
    unresolved_questions: list[str]
    risk_flags: list[str]
    verification_summary: str
    token_budget: int
    generated_at: datetime
    context_hash: str
```

## 5. SourceEvidenceStore 接口

```python
class SourceEvidenceStore(Protocol):
    def put_paper_card(self, paper: PaperCard) -> str: ...
    def get_paper_card(self, paper_id: str) -> PaperCard: ...
    def put_evidence(self, evidence: EvidenceRef) -> str: ...
    def get_evidence(self, evidence_id: str) -> EvidenceRef: ...
    def search_evidence(self, query: str, filters: dict) -> list[EvidenceRef]: ...
    def verify_source(self, evidence_id: str, verification_ref: str) -> EvidenceRef: ...
```

必须保证：

- 稳定 ID。
- 正式证据有版本。
- 原始来源可定位。
- 更新不能覆盖旧版本。
- `human_verified` 必须关联人工审批。

## 6. ContextProvider 接口

```python
class ContextProvider(Protocol):
    def build_context(
        self,
        task_ref: str,
        required_context_types: list[str],
        token_budget: int,
    ) -> ContextBundle: ...
```

标准步骤：

1. 读取当前任务和阶段。
2. 获取当前有效协议。
3. 获取正式人工决定。
4. 检索相关证据。
5. 获取短期和长期 Memory。
6. 去重、排序和裁剪。
7. 保留核验状态和来源引用。
8. 计算 `context_hash`。

## 7. 上下文优先级

```text
人工批准的正式决定
→ 当前阶段有效协议
→ source_verified / human_verified 证据
→ 已验证工件摘要
→ 当前任务短期 Memory
→ 项目长期 Memory
→ 未核验候选内容
```

禁止：

- 未核验内容覆盖正式决定。
- 旧协议覆盖新版本。
- 因 Token 不足删除关键审批或风险。
- 推测与事实混合。
- 完整 PDF、代码、数据或日志进入 `ContextBundle`。

## 8. GraphRAG 后续实现

Phase 1 只定义接口。后续再实现：

```text
文档解析 → 切块 → 元数据 → 嵌入 → 向量检索
→ 图关系检索 → 结果融合 → RRF → MMR → 原文定位
```

MVP 约束：

- 一个多语言嵌入模型。
- 一个统一向量维度。
- 不同维度不能进入同一 Collection。
- 检索结果不等于正式证据。

## 9. Phase 1 实施步骤

1. 实现 `EvidenceStatus`、`EvidenceRelation`、`MemoryType`。
2. 实现 `SourceLocation`、`EvidenceRef`、`MemoryRef`。
3. 实现最小 `PaperCard` 和 `EvidenceMatrix`。
4. 实现 `SourceEvidenceStore` 接口。
5. 实现 `ContextBundle` 和 `ContextProvider` 接口。
6. 编写 MockContextProvider。
7. 编写不变量测试和输入输出示例。

## 10. 必须测试

- 未核验证据不能自动变成 `human_verified`。
- 正式 EvidenceRef 必须有来源位置。
- ContextBundle 拒绝完整 PDF、代码、数据和二进制。
- Memory 不能代替 ApprovalRecord。
- 多版本协议只选当前有效版本。
- Token 裁剪不能删除当前任务、审批、关键风险和正式协议。

## 11. Phase 1 交付物

```text
EvidenceStatus / EvidenceRelation
SourceLocation / EvidenceRef
PaperCard 最小模型
MemoryRef
ContextBundle
SourceEvidenceStore 接口
ContextProvider 接口
MockContextProvider
单元测试
模块 README
输入输出示例
```

## 12. 完成定义

- 模型可序列化。
- 引用有稳定 ID。
- 上下文不含大对象。
- 核验状态不可越权。
- Memory 与 Decision 分离。
- ContextBundle 能被 AgentContract 消费。
- 类型检查和测试通过。
- 未提前实现完整 GraphRAG。

## 13. 后续阶段

- Phase 2：手动证据和 Mock 上下文进入最小闭环。
- Phase 3—5：论文解析、PaperCard 抽取、EvidenceMatrix、GraphRAG 和黄金集。
- Phase 6 以后：长期项目知识、证据冲突图、权限和多项目隔离。

## 14. 验收问题

1. Agent 看到的信息是否都有来源？
2. 未核验内容是否可能进入正式结论？
3. Memory、Evidence、Decision 是否分离？
4. Token 限制下是否保留关键内容？
5. 是否能从 ContextBundle 反查原文？
