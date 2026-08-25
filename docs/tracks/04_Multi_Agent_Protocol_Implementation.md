# STEM-SCI 多 Agent 与研究协议编译实施说明

> 技术线：多 Agent
> 目标：用统一契约组织六类专业科研角色，并通过 Research Protocol Compiler 将自然语言研究构想转化为结构化科研协议候选。
> 当前阶段：Phase 1 只实现 Agent 契约、协议模型、Reviewer 输出和权限边界。
> 核心原则：Agent 负责 Reasoning，不负责 Governance 和 Execution。

---

## 1. 最终要解决的问题

1. 不同科研角色应该输入什么、输出什么。
2. Agent 如何提出工具请求和人工审批请求。
3. 六类 Agent 如何避免职责重复。
4. Reviewer 如何保持独立。
5. Research Protocol Compiler 如何生成可验证协议。
6. Agent 为什么不能直接修改阶段、审批、数据和正式结果。
7. 如何记录 Agent、Prompt 和运行版本。

## 2. 六类专业 Agent

### 导师规划 Agent

负责研究范围、研究问题树、可行性问题和项目路线。

### 证据综述 Agent

负责 SearchProtocol、PaperCard 综合、EvidenceMatrix 候选、冲突证据和研究空白；不执行真实检索。

### 研究设计 Agent

负责候选设计、Estimand、CausalDAG、变量、样本、测量和 PreregisteredAnalysisPlanDraft；不批准正式设计。

### 科研计算与数据分析 Agent

负责数据问题诊断、处理建议、CodeSpecificationDraft、方法和解释边界；不修改真实数据和统计结果。

### 论文写作 Agent

只使用已核验文献、已批准方法、已验证结果和已确认解释边界，输出 AtomicClaimCandidate、ClaimEvidenceMap 和 ManuscriptDraft。

### 独立审稿 Agent

包括 Citation、Method、Reproducibility、Pedagogy Reviewer 和 Review Arbiter，只输出审稿意见。

## 3. Agent 统一契约

### AgentInput

```python
class AgentInput(BaseModel):
    agent_run_id: str
    task_ref: str
    context_bundle_ref: str
    allowed_tool_capabilities: list[str]
    allowed_output_types: list[str]
    policy_version: str
    prompt_template_version: str
```

### AgentResult

```python
class AgentResult(BaseModel):
    agent_run_id: str
    agent_id: str
    agent_version: str
    candidate_artifact_refs: list[str]
    tool_requests: list[str]
    approval_requests: list[str]
    risk_flags: list[str]
    unresolved_questions: list[str]
    recommendations: list[str]
    confidence: float | None
    created_at: datetime
```

禁止字段：

```text
new_current_stage
approved
freeze_dataset
official_result
publish
```

### AgentCapability

```python
class AgentCapability(BaseModel):
    agent_id: str
    supported_task_types: list[str]
    allowed_tool_capabilities: list[str]
    allowed_output_types: list[str]
    forbidden_actions: list[str]
```

### ToolRequest

```python
class ToolRequest(BaseModel):
    request_id: str
    capability: str
    input_refs: list[str]
    required_output_types: list[str]
    reason: str
```

只能交给 Controller。

### ApprovalRequest

```python
class ApprovalRequest(BaseModel):
    request_id: str
    artifact_ref: str
    approval_type: str
    reason: str
    risk_summary: str
```

## 4. Reviewer 数据对象

### ReviewFinding

```python
class ReviewFinding(BaseModel):
    finding_id: str
    reviewer_type: str
    artifact_ref: str
    severity: str
    category: str
    description: str
    evidence_refs: list[str]
    suggested_action: str
```

### RevisionRequest

```python
class RevisionRequest(BaseModel):
    revision_id: str
    artifact_ref: str
    required_changes: list[str]
    blocking: bool
    triggered_by_refs: list[str]
```

### ReviewReport

```python
class ReviewReport(BaseModel):
    review_report_id: str
    finding_refs: list[str]
    revision_request_refs: list[str]
    overall_recommendation: str
```

Reviewer 不能修改工件、结果卡、阶段和审批，也不能直接发布。

## 5. Research Protocol Compiler

### 输入

```text
研究主题、目标用户、研究对象、教学场景、资源和时间、可用数据、伦理条件、文献证据
```

### 输出

```text
ResearchContract
FeasibilityReport
ResearchQuestion
Hypothesis
Estimand
CausalDAG
StudyProtocol
InterventionProtocol
ProgrammingTaskSpecification
HintPolicy
CodeRubric
UnitTestSpecification
DataCollectionSchema
PreregisteredAnalysisPlan
QualityGatePlan
PreregistrationSnapshot
```

### 编译流程

```text
自然语言研究意图
→ 意图和实体解析
→ 缺失字段识别
→ 可行性检查
→ 文献需求
→ 研究问题候选
→ 候选设计
→ 结构化协议候选
→ Research Unit Test
→ Gate
→ Human Approval
```

Compiler 输出默认是候选，不是正式批准工件。

## 6. 协议核心模型

### ResearchContract

```python
class ResearchContract(BaseModel):
    contract_id: str
    topic: str
    population: str | None
    context: str | None
    intervention: str | None
    comparator: str | None
    outcomes: list[str]
    constraints: list[str]
    exclusions: list[str]
    unresolved_questions: list[str]
```

### ResearchQuestion

```python
class ResearchQuestion(BaseModel):
    question_id: str
    text: str
    population: str
    intervention: str | None
    comparator: str | None
    outcomes: list[str]
    context: str
    approval_ref: str | None
```

### Estimand

```python
class Estimand(BaseModel):
    estimand_id: str
    population: str
    treatment: str
    comparator: str
    outcome: str
    time: str
    summary_measure: str
```

### StudyProtocol

```python
class StudyProtocol(BaseModel):
    protocol_id: str
    research_question_refs: list[str]
    hypothesis_refs: list[str]
    estimand_ref: str
    design_type: str
    sampling_plan_ref: str
    intervention_protocol_ref: str
    measurement_plan_ref: str
    ethics_ref: str
    approval_ref: str | None
```

### PreregisteredAnalysisPlan

必须包含：

```text
primary_outcomes
secondary_outcomes
confirmatory_models
covariates
exclusion_rules
missing_data_strategy
outlier_strategy
alpha
multiple_comparison_strategy
effect_size_requirements
confidence_interval_requirements
exploratory_analysis_policy
approval_ref
frozen_at
```

## 7. AtomicClaim

一个 AtomicClaim 只能有一个类型：

```text
LITERATURE
RESULT
METHOD
INTERPRETATION
SPECULATION
LIMITATION
```

复合句必须拆分 RESULT 和 INTERPRETATION，不能使用 `RESULT + INTERPRETATION`。

## 8. 与上下文组接口

Agent 只接收 `ContextBundleRef`，其中明确区分 Evidence、Decision、Protocol、Artifact、Memory 和 UnresolvedQuestion。

禁止 Agent 直接读取整个数据库、完整 PDF 或未核验模型记忆。

## 9. 与工具组接口

```text
AgentResult → Controller → OperatorRegistry → OperatorRun
```

Agent 不能直接执行 Shell、Python、SPSS 或 DataFreeze。

## 10. 与工作流组接口

工作流组消费：

```text
AgentResult
ApprovalRequest
ToolRequest
ReviewFinding
RevisionRequest
```

工作流负责权限、状态、工具调用、Gate 和人工审批。

## 11. Phase 1 实施步骤

1. 实现 AgentInput、AgentResult。
2. 实现 AgentCapability。
3. 实现 ToolRequest、ApprovalRequest。
4. 实现 ReviewFinding、RevisionRequest、ReviewReport。
5. 实现 ResearchContract、ResearchQuestion、Estimand、StudyProtocol。
6. 实现 PreregisteredAnalysisPlan 最小模型。
7. 实现 AtomicClaim 约束。
8. 编写权限和不变量测试。

## 12. 必须测试

1. AgentResult 不允许阶段字段。
2. AgentResult 不允许直接批准工件或冻结数据。
3. ToolRequest 必须通过 Controller。
4. Reviewer 只能输出只读审稿对象。
5. 未批准 PreregisteredAnalysisPlan 不能冻结。
6. AtomicClaim 只允许一个类型。
7. 写作 Agent 不能引用未核验证据。
8. Compiler 输出默认为候选状态。
9. AgentCapability 限制工具权限。

## 13. Phase 1 交付物

```text
AgentInput / AgentResult / AgentCapability
ToolRequest / ApprovalRequest
ReviewFinding / RevisionRequest / ReviewReport
ResearchContract / ResearchQuestion / Hypothesis
Estimand / CausalDAGRef / StudyProtocol
PreregisteredAnalysisPlan
AtomicClaim
权限测试、README、示例
```

## 14. 完成定义

- 六类 Agent 使用统一契约。
- Agent 权限清晰。
- Agent 不能推进阶段和直接执行工具。
- Reviewer 保持只读。
- Compiler 输出候选协议。
- AtomicClaim 类型单一。
- 可与上下文、工具和工作流对接。
- 测试通过。
- 未提前实现完整 Agent 业务。

## 15. 后续阶段

- Phase 2：Mock Agent、最小 AtomicClaim、接入 ContextBundle 和 Controller。
- Phase 5：正式 Prompt、Research Protocol Compiler、文献和设计 Agent。
- Phase 7：动态 Reviewer、多轮修订、工作流消融。

## 16. 验收问题

1. Agent 是否只负责专业推理？
2. Agent 是否可能直接控制流程？
3. Agent 输出是否结构化？
4. Reviewer 是否独立？
5. Compiler 是否生成可验证协议而不是一段文字？
6. AtomicClaim 是否能追溯证据或执行结果？
