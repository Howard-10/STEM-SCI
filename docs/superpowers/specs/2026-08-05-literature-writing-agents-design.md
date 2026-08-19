# 综述 Agent 与论文写作 Agent 内部设计

**日期：** 2026-08-05
**状态：** 设计已确认，待编写实施计划
**适用项目：** STEM-SCI Phase 2 Agent 内部能力

## 1. 目标

在不改变现有六智能体拓扑、Controller 路由和人工审批边界的前提下，为以下两个角色增加可运行的内部能力：

- `evidence_review`：基于项目知识库中已核验语料完成限定语料证据综合。
- `paper_writing`：基于已核验证据、已批准方法和已验证结果生成中英文论文草稿。

第一版使用真实 GPT 模型和现有本地知识库，不接在线文献检索，不声称完成完整系统综述，不自动发布论文。

## 2. 已确认的设计决策

1. 模型接入采用 Provider 抽象，当前部署使用 GPT；Agent 内部不绑定具体厂商 SDK 或模型名称。
2. 综述定位是“限定语料证据综合”，不是完整系统综述或 PRISMA 综述。
3. 中文稿和英文稿共享同一个 `AtomicClaimGraph`，分别生成语言表达，并执行双语一致性校验。
4. 每个 Agent 在一次 Controller 调度中运行内部多阶段流水线，不增加子 Agent 网络。
5. Agent 只能生成候选工件和结构化风险，不能推进阶段、批准工件、冻结数据、修改结果或发布论文。
6. 真实 GPT 调用只通过环境变量配置；API Key 不进入代码、日志、工件正文或 Git。

## 3. 范围边界

### 3.1 本阶段包含

- GPT 结构化输出 Provider。
- 综述 Agent 的语料审计、筛选、PaperCard、证据矩阵、冲突和研究空白流水线。
- 论文写作 Agent 的输入审计、AtomicClaimGraph、IMRaD 提纲、中英文稿和一致性检查流水线。
- 结构化工件正文存储和版本引用。
- Controller 对两个 Agent 的上下文组装、预算记录和现有审批接入。
- Fake Provider 驱动的单元、集成和端到端测试。

### 3.2 本阶段不包含

- 在线数据库检索、自动补全文献和完整 PRISMA 流程。
- GraphRAG、向量数据库或未经核验的模型记忆。
- 自动修改研究设计、数据、统计结果或预注册方案。
- 自动投稿、发表、版权处理或生产环境密钥管理。
- 把一次 Agent 调度拆成多个新的 Controller Agent 节点。

## 4. 总体架构

```text
Controller
   |
   +--> EvidenceReviewAgent
   |       corpus audit
   |         -> screening
   |         -> PaperCard extraction
   |         -> evidence matrix
   |         -> conflicts and gaps
   |         -> bounded synthesis
   |
   +--> PaperWritingAgent
           input audit
             -> AtomicClaimGraph
             -> IMRaD outline
             -> Chinese manuscript
             -> English manuscript
             -> bilingual consistency

Both pipelines use:
  LLMProvider -> StructuredGenerator -> PromptRegistry
  ArtifactContentStore -> ArtifactStore -> AgentRunStore
```

两个 Agent 仍通过现有 `AgentInput`、`AgentResult`、`ToolRequest`、`ApprovalRequest` 和 `ReviewFinding` 与 Controller 通信。Agent 不直接调用其他 Agent，也不直接访问 SQLite。

建议的新增模块边界如下：

```text
backend/src/stem_sci/agents/runtime/
  provider.py
  structured_generator.py
  prompt_registry.py

backend/src/stem_sci/agents/evidence_pipeline/
  models.py
  stages.py
  validators.py
  pipeline.py
  prompts/

backend/src/stem_sci/agents/writing_pipeline/
  models.py
  stages.py
  validators.py
  bilingual.py
  pipeline.py
  prompts/

backend/src/stem_sci/artifacts/content_store.py
```

现有 `EvidenceReviewAgent` 和 `PaperWritingAgent` 保持对外类名，由它们负责调用对应 Pipeline 并把工件引用汇总成 `AgentResult`。

## 5. GPT Provider

### 5.1 接口

Provider 只负责一次结构化生成，不负责科研语义、审批和工件状态：

```python
class LLMProvider(Protocol):
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        model: str,
        prompt_version: str,
    ) -> GenerationResult: ...
```

`GenerationResult` 至少包含：

```text
parsed_output
model
prompt_version
request_id
input_tokens
output_tokens
latency_ms
response_hash
retry_count
```

### 5.2 配置

部署配置使用以下环境变量，实际值不写入仓库：

```text
STEM_SCI_LLM_PROVIDER=gpt
STEM_SCI_LLM_BASE_URL=<GPT-compatible endpoint>
STEM_SCI_LLM_API_KEY=<local secret>
STEM_SCI_LLM_MODEL=<deployment-selected GPT model>
STEM_SCI_LLM_TIMEOUT_SECONDS=60
STEM_SCI_MAX_LLM_CALLS=<per-run budget>
```

Provider 必须使用超时、有限重试和结构化 Schema 校验。API Key 不能进入异常文本、请求审计正文或模型生成的工件。

### 5.3 失败规则

- 网络失败或超时：有限重试，最终记录 `LLM_PROVIDER_UNAVAILABLE`。
- JSON 解析失败：使用相同 Prompt 版本重试，仍失败则 `FAILED`。
- Schema 校验失败：不得把原始自由文本当作候选工件保存。
- 预算耗尽：记录 `LLM_BUDGET_EXCEEDED`，停止当前流水线。
- Provider 不可用时不能降级到模型记忆或虚构内容。

## 6. 综述 Agent

### 6.1 上下文

Controller 组装 `EvidenceReviewContext`，不向 Agent 暴露数据库连接：

```text
project_id
research_scope_ref
research_questions
inclusion_exclusion_criteria
verified_evidence_refs
source_refs
context_hash
corpus_time_boundary
unresolved_questions
```

Agent 只读取项目范围内允许的 `EvidenceRef` 和 `SourceChunk`。来源状态必须属于 `SOURCE_VERIFIED`、`HUMAN_VERIFIED` 或显式允许的演示语料。文献内容按来源分批进入模型上下文，不能把整个数据库直接交给模型。

### 6.2 流水线

1. **语料审计**：生成 `CorpusCoverageReport`，统计来源数量、年份、研究对象、设计、主题覆盖和缺失区域。
2. **文献筛选**：为每个来源生成 `ScreeningDecision`，包含 `INCLUDE`、`EXCLUDE` 或 `UNCERTAIN`、筛选理由、标准引用和证据引用。
3. **PaperCard 抽取**：生成标题、研究问题、对象、场景、设计、样本、干预、结局、主要发现、局限和证据引用。原文没有的信息保持空值。
4. **证据矩阵**：按研究问题组织 `EvidenceMatrixRow`，记录 `SUPPORTING`、`CONTRASTING` 或 `MENTIONING` 关系、设计、样本、结果方向和适用边界。
5. **冲突与研究空白**：生成 `EvidenceConflictMap` 和 `ResearchGapReport`。空白必须限定为“在当前限定语料中未发现”。
6. **限定语料综合**：生成 `BoundedEvidenceSynthesis`，包含背景、主题综合、方法差异、冲突证据、研究空白、项目启示和语料局限。

### 6.3 工件

```text
SearchProtocolCandidate
CorpusCoverageReport
ScreeningLedger
PaperCardCollection
EvidenceMatrixCandidate
EvidenceConflictMap
ResearchGapReport
EvidenceSufficiencyReport
BoundedEvidenceSynthesis
LiteratureNeedUpdate
```

### 6.4 综述硬校验

- 每条事实性陈述至少关联一个当前项目的 `EvidenceRef`。
- 引用来源状态必须满足上下文白名单。
- PaperCard 字段没有原文依据时必须为空，不能由模型补写。
- 按来源哈希和稳定文献标识去重。
- 研究空白必须包含语料范围限定。
- 证据不足时可以输出覆盖报告和风险，但不能输出肯定性综合结论。
- 综合置信度由覆盖率、引用完整率和冲突比例计算，不接受模型自报置信度作为唯一依据。

## 7. 论文写作 Agent

### 7.1 上下文

Controller 组装 `WritingContextBundle`：

```text
project_id
approved_research_scope
verified_evidence_refs
paper_cards
evidence_matrix
approved_study_protocol
validated_result_cards
interpretation_boundaries
prior_review_findings
output_language: zh-CN | en-US
```

缺少 `validated_result_cards` 时，Agent 可以生成引言、方法、讨论框架和局限性，但不能生成具体 Results 结论。

### 7.2 流水线

1. **输入审计**：检查工件状态、项目归属、版本、哈希和审批引用。缺失输入输出 `WritingSufficiencyReport`，不让模型自行补全。
2. **AtomicClaimGraph**：为每个主张分配稳定 ID、唯一类型、证据引用、结果引用、方法引用、审批引用、关系、强度和目标章节。
3. **IMRaD 提纲**：生成标题、摘要、引言、方法、结果、讨论、局限、复现声明和参考文献，并把章节绑定到允许使用的主张 ID。
4. **中文稿生成**：从唯一主张图谱渲染 `ManuscriptDraftZh`。
5. **英文稿生成**：仍从同一主张图谱独立渲染 `ManuscriptDraftEn`，不是对中文自由翻译。
6. **一致性校验**：比较主张数量、主张 ID、引用、数字、结果方向、因果强度和局限性。

### 7.3 AtomicClaim 规则

允许的唯一类型为：

```text
LITERATURE | RESULT | METHOD | INTERPRETATION | SPECULATION | LIMITATION
```

- `LITERATURE` 必须有核验文献引用。
- `RESULT` 必须有已验证结果引用。
- `METHOD` 必须有已批准方法引用。
- `INTERPRETATION` 必须关联结果主张和解释边界。
- `SPECULATION` 必须明确标记为推测。
- `LIMITATION` 必须指向证据、设计或数据限制。

禁止把 `RESULT` 和 `INTERPRETATION` 合并成一个主张。准实验结果不能写成无限制因果结论，未执行的分析不能进入 Results。

### 7.4 工件

```text
AtomicClaimCollection
ClaimEvidenceMap
ManuscriptOutline
ManuscriptDraftZh
ManuscriptDraftEn
LimitationsDraft
ReproducibilityStatement
BilingualConsistencyReport
WritingSufficiencyReport
```

### 7.5 双语校验

两种语言必须共享：

- `claim_id`
- 数字和统计量
- 引用来源
- 结论强度
- 局限性
- 章节关系

出现数字、引用、结论强度或主张集合不一致时，输出 `BILINGUAL_MISMATCH` 并阻止草稿进入 Controller 审批。

## 8. 工件和 Controller 集成

现有 `ArtifactStore` 继续保存版本化 `ArtifactRef`；新增 `ArtifactContentStore` 保存结构化正文、Schema 版本、正文哈希和生成元数据。`ResearchState` 只保存引用，不保存长文本。

Controller 的单次调度流程保持为：

```text
创建 AgentInput
→ 组装 EvidenceReviewContext 或 WritingContextBundle
→ 调用对应 Pipeline
→ 保存工件正文和 ArtifactRef
→ 汇总 AgentResult
→ 记录 AgentRunRecord
→ 执行现有人工审批 Gate
```

现有六智能体连接逻辑不增加子节点。综述和写作内部阶段属于 Agent 实现细节，最终仍只返回一个 AgentResult。

需要同步扩展：

- Agent capability 的输出工件类型。
- Controller 的写作上下文组装。
- `AgentRunRecord` 的 LLM 调用元数据引用。
- `BudgetState` 的 LLM 调用消耗和每次运行上限。
- OpenAPI/审计接口对结构化工件正文的只读查询能力。

## 9. 状态和错误处理

使用现有 `TaskStatus`、`RunStatus` 和 `ArtifactStatus`，不另造并行生命周期。流水线内部错误映射如下：

| 情况 | 记录 | 处理 |
|---|---|---|
| GPT 超时或网络失败 | `LLM_PROVIDER_UNAVAILABLE` | 有限重试，失败后 `FAILED` |
| 非法 JSON 或 Schema | `INVALID_STRUCTURED_OUTPUT` | Schema 重试，仍失败则 `FAILED` |
| 引用不存在或跨项目 | `INVALID_EVIDENCE_REFERENCE` | 丢弃该候选，不保存正文 |
| 证据或结果缺失 | `INCOMPLETE_RESULT_INPUT` | 生成缺口报告，不生成强结论 |
| 中英文不一致 | `BILINGUAL_MISMATCH` | 草稿 `BLOCKED`，不得审批 |
| LLM 调用超预算 | `LLM_BUDGET_EXCEEDED` | 停止流水线，保留审计记录 |
| 语料覆盖不足 | `INSUFFICIENT_CORPUS_COVERAGE` | 生成覆盖和风险报告，限制综合结论 |

任何错误都不能触发 Agent 自行改变 `ResearchState.current_stage`、批准工件、冻结数据或发布论文。

## 10. 测试策略

### 10.1 Provider 测试

- 有效结构化响应。
- 超时和网络错误的有限重试。
- 非法 JSON 和 Schema 错误。
- 预算耗尽后不再调用模型。
- API Key 不出现在日志、错误和工件正文。

### 10.2 综述 Agent 测试

- 证据引用完整性和项目隔离。
- 重复来源去重。
- `INCLUDE`、`EXCLUDE`、`UNCERTAIN` 筛选。
- 冲突证据保持双向引用。
- 研究空白始终带限定语。
- 未核验证据不能进入综合结论。

### 10.3 论文写作 Agent 测试

- AtomicClaim 只能有一个类型。
- `RESULT` 没有验证结果时必须失败或生成缺口报告。
- 未执行分析不能进入 Results。
- 章节不能引用未授权主张。
- 中英文数字、引用、主张 ID 和结论强度不一致时必须阻断。
- 双语稿共享同一主张图谱，而不是互相产生新主张。

### 10.4 Controller 集成测试

- 综述 Agent 仍由 `SCOPED` 路由。
- 写作 Agent 仍由 `ANALYZED` 路由。
- Agent 只能返回候选引用并等待人工 Gate。
- 现有审批、REWORK、ReviewFinding 路由保持不变。
- Artifact、AgentRun、RouteDecision 和 LLM 元数据可以按项目查询。

### 10.5 运行级测试

所有 CI 使用 Fake GPT Provider，不访问外部 API。真实 GPT 调用只作为本地手动 smoke test，并且必须显式设置环境变量和预算。

## 11. 验收标准

完成实现后必须满足：

1. 两个 Agent 都能在 Fake Provider 下完成端到端流水线。
2. 综述结果中的事实性内容可以回指项目内已核验来源。
3. 论文草稿中的每个主张都有唯一类型和允许的证据/结果引用。
4. 中文和英文稿共享同一主张图谱，且一致性检查通过。
5. 证据不足、结果缺失、Provider 失败和预算耗尽都会产生可审计状态。
6. Agent 无法直接推进阶段、批准工件、修改数据或发布论文。
7. 现有六智能体 Controller 路由、审批和 REWORK 测试全部保持通过。
8. GPT 密钥和完整请求正文不会进入 Git 或普通日志。

## 12. 后续实施顺序

1. 先实现 Provider、结构化生成器、PromptRegistry 和预算计数。
2. 再实现综述 Agent 的领域模型、验证器和流水线。
3. 再实现 `ArtifactContentStore` 和 `EvidenceReviewContext` 持久化接入。
4. 实现写作 Agent 的 AtomicClaimGraph、双语渲染和一致性校验。
5. 接入 Controller、审计 API 和现有人工审批 Gate。
6. 用 Fake Provider 完成全套测试后，再做一次本地 GPT smoke test。
