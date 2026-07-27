# STEM-SCI 工作流与 Controller 实施说明

> 技术线：工作流
> 目标：建立唯一、确定、可恢复、可审计的科研状态机，协调上下文、多 Agent、Operator、Gate、风险和人工审批。
> 当前阶段：Phase 1 实现状态、权限、Reducer、Controller、RouteDecision、Approval 和不变量测试。
> 核心原则：只有 Controller 可以推进 `current_stage`。

---

## 1. 最终要解决的问题

1. 项目当前处于什么阶段。
2. 下一步调用谁。
3. 什么条件允许进入下一阶段。
4. 什么情况返工、阻塞或等待人工。
5. 局部错误影响多大范围。
6. 多个并行输出如何安全合并。
7. interrupt/resume 如何避免重复副作用。
8. 每次路由为什么发生、由谁决定。

## 2. 负责范围

### 2.1 负责

- `ProjectStage`、`TaskStatus`、`ArtifactStatus`、`RunStatus`。
- `DecisionScope`、`ResearchState`、Reducer。
- Controller、Merger、Router、RulePolicy。
- `GateResult`、`RouteDecision`、`ApprovalRecord`。
- interrupt/resume、幂等键、失败恢复。
- RiskProfile 和 BudgetState 的消费。
- 状态审计日志。

### 2.2 不负责

- 不执行文献搜索和代码。
- 不生成 Agent 专业结论。
- 不存完整 PDF、数据、代码和大日志。
- 不决定具体科研方法内容。
- 不直接修改统计结果。

## 3. 顶层状态机

```text
INTAKE
→ SCOPED
→ SEARCH_PROTOCOL_APPROVED
→ EVIDENCE_READY
→ RESEARCH_QUESTION_APPROVED
→ STUDY_PROTOCOL_APPROVED
→ DATA_READY
→ ANALYZED
→ DRAFTED
→ VERIFIED
→ RELEASED
```

异常状态：

```text
REWORK
BLOCKED
WAITING_HUMAN
FAILED
```

## 4. 状态分层

### ProjectStage

整个项目的主流程阶段。

### TaskStatus

```text
DRAFT / READY / RUNNING / REVIEW / DONE
REWORK / BLOCKED / WAITING_HUMAN / FAILED
```

### ArtifactStatus

```text
DRAFT / CANDIDATE / VALIDATED / APPROVED
REJECTED / BLOCKED / SUPERSEDED
```

### RunStatus

```text
PENDING / RUNNING / SUCCEEDED / FAILED / TERMINATED / BLOCKED
```

不能用一个状态表达全部层级。

## 5. DecisionScope

```text
RUN
ARTIFACT
TASK
STAGE
PROJECT
```

示例：

```text
学生代码访问网络 → RUN
单篇 DOI 无效 → ARTIFACT
统计执行失败 → RUN 或 TASK
FrozenDataset 哈希异常 → STAGE
无合法数据或伦理许可 → PROJECT
```

原则：使用能够表达风险影响的最小作用域。

## 6. ResearchState

ResearchState 只保存引用和运行上下文：

```python
class ResearchState(TypedDict):
    current_stage: ProjectStage
    task_status: dict[str, TaskStatus]
    task_ledger: list[str]
    progress_ledger: list[str]
    evidence_ledger: list[str]
    artifact_refs: list[str]
    data_asset_refs: list[str]
    execution_run_refs: list[str]
    protocol_refs: list[str]
    research_test_result_refs: list[str]
    risk_profile_refs: list[str]
    route_decision_refs: list[str]
    agent_run_refs: list[str]
    approval_request_refs: list[str]
    budget_state: str | None
    recent_rounds: list[str]
    short_memory_summary: str | None
    long_memory_refs: list[str]
    risk_flags: list[str]
    error_log: list[str]
```

禁止存入 PDF、完整数据、学生代码、科研代码、图片、SPSS 输出和完整日志。

## 7. Merger

Controller Merger 负责：

1. 验证 AgentResult、OperatorRun、Reviewer 输出。
2. 检查越权字段。
3. 合并候选工件引用、风险、工具请求和审批请求。
4. 更新三本账本。
5. 拒绝任何非 Controller 的阶段修改。

## 8. Reducer

规则：

- 引用列表去重合并。
- 错误日志追加。
- 风险标记取并集。
- 账本 append-only。
- 版本冲突保留双方并触发处理。
- 后到结果不能覆盖正式引用。
- `current_stage` 不走通用 Reducer。

## 9. Gate 与 RouteDecision

### ResearchTestResult

```python
class ResearchTestResult(BaseModel):
    test_id: str
    artifact_id: str
    status: str
    severity: str
    evidence_refs: list[str]
    failure_reason: str | None
    repair_action: str | None
    executed_at: datetime
```

### GateResult

```python
class GateResult(BaseModel):
    gate_id: str
    gate_version: str
    artifact_id: str
    decision: str
    decision_scope: DecisionScope
    blocked_target_ids: list[str]
    research_test_result_refs: list[str]
    risk_profile_ref: str | None
    missing_fields: list[str]
    risk_flags: list[str]
    next_action: str
    created_at: datetime
```

### RouteDecision

```python
class RouteDecision(BaseModel):
    decision_id: str
    current_stage: ProjectStage
    selected_route: str
    decision_scope: DecisionScope
    blocked_target_ids: list[str]
    gate_result_refs: list[str]
    risk_profile_ref: str | None
    budget_snapshot_ref: str | None
    triggered_rules: list[str]
    final_decider: str
    policy_version: str
    created_at: datetime
```

## 10. 路由优先级

```text
安全与科研诚信硬规则
→ 人工审批规则
→ Research Unit Test / Gate
→ 风险评分
→ 预算策略
→ 模型建议
```

模型建议不能覆盖前面的规则。

## 11. ApprovalRecord

```python
class ApprovalRecord(BaseModel):
    approval_id: str
    artifact_id: str
    artifact_version: int
    decision: str
    decided_by: str
    decided_at: datetime
    reason: str | None
    risk_acknowledgements: list[str]
    previous_approval_ref: str | None
    idempotency_key: str
```

必须人工审批：研究问题、研究设计、文献纳排标准、伦理边界、主要结果变量、预注册计划、数据处理方案、分析计划修订、关键结果解释和最终发布。

## 12. interrupt / resume

- interrupt 生成稳定 `approval_request_id`。
- resume 携带审批引用。
- 使用幂等键。
- 同一审批重复 resume 不产生重复 FrozenDataset。
- 恢复前验证工件版本。
- 恢复后生成 RouteDecision。
- 所有恢复写入审计日志。

## 13. 失败和返工

```text
第一次失败 → 原模块定向修复
第二次失败 → 拆分任务或替换 Operator
第三次失败 → WAITING_HUMAN
```

直接 BLOCKED：无合法数据、无伦理许可、虚假正式来源、FrozenDataset 哈希异常、正式运行读取错误数据版本。

## 14. Phase 1 实施步骤

1. 实现所有状态枚举。
2. 实现 ResearchState 和三本账本。
3. 实现 Reducer。
4. 实现 AgentResult / OperatorRun 权限校验。
5. 实现 GateResult 和 RouteDecision。
6. 实现 ApprovalRecord 与 interrupt/resume 契约。
7. 实现少量可解释 RulePolicy。
8. 编写不变量测试。

## 15. 必须测试

1. Agent、Operator、Reviewer 均不能修改 `current_stage`。
2. ResearchState 拒绝大对象。
3. Reducer 不覆盖已有引用。
4. Run 错误不自动阻塞 Project。
5. 未批准预注册计划不能进入数据采集。
6. 重复 resume 不产生重复副作用。
7. DecisionScope 使用最小作用域。
8. 模型建议不能覆盖硬规则。
9. ApprovalRecord 必须绑定工件版本。
10. 每次状态迁移都产生 RouteDecision。

## 16. Phase 1 交付物

```text
状态枚举
ResearchState 与三本账本
Reducer
Controller Merger / Rule Router
ResearchTestResult / GateResult / RouteDecision
RiskProfile / BudgetState
ApprovalRecord / interrupt-resume 契约
不变量测试、README、示例
```

## 17. 完成定义

- 只有 Controller 能迁移阶段。
- State 只存引用。
- 并行合并安全。
- 所有路由有 RouteDecision。
- Approval 可恢复且幂等。
- 局部错误不扩大。
- 硬规则优先级正确。
- 测试通过。

## 18. 后续阶段

- Phase 2：串起最小真实闭环。
- Phase 3：实现具体 Gate 和 Research Unit Tests。
- Phase 7：风险动态路由、Reviewer 触发、预算和停滞检测。

## 19. 验收问题

1. 是否存在非 Controller 组件修改阶段？
2. 每次路由是否可审计？
3. 局部错误是否被错误扩大？
4. 审批恢复是否幂等？
5. 并行结果是否可能覆盖正式引用？
