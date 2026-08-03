# STEM-SCI Phase 1：六类 Agent 脚手架实施说明

## 1. 本次完成内容

本次工作依据以下设计材料完成：

- `STEM-SCI助研多Agent流程控制优化汇报稿.md`
- `docs/tracks/04_Multi_Agent_Protocol_Implementation.md`
- `docs/tracks/STEM_SCI_Multi_Agent_Workflow.md`

本次没有把系统改造成自由聊天式多 Agent，也没有实现自动写论文。当前已经完成六类专业 Agent 的统一契约、角色边界、Controller 注册与结果校验，以及“研究想法 → 导师规划候选工件 → WAITING_HUMAN”的最小纵向闭环。

## 2. 六类 Agent

| Agent | 代码类名 | 当前职责 |
|---|---|---|
| 导师规划 Agent | `MentorPlanningAgent` | 研究范围、研究问题树、可行性和项目路线候选 |
| 证据综述 Agent | `EvidenceReviewAgent` | 检索协议、论文筛选、证据矩阵和研究空白候选 |
| 研究设计 Agent | `ResearchDesignAgent` | Estimand、研究方案、任务、量规和预注册分析计划候选 |
| 科研计算与数据分析 Agent | `DataAnalysisAgent` | 数据审计、分析规格、代码规格和结果解释边界候选 |
| 论文写作 Agent | `PaperWritingAgent` | AtomicClaim、主张—证据映射、论文结构和复现声明候选 |
| 独立审稿 Agent | `IndependentReviewAgent` | 引用、方法、复现和教学逻辑审查意见候选 |

代码位置：

```text
backend/src/stem_sci/agents/
├── base.py
├── contracts.py
├── planner.py
├── evidence.py
├── design.py
├── analysis.py
├── writing.py
└── reviewer.py
```

## 3. 统一 Agent 契约

### AgentInput

Controller 为每次运行提供：

- `agent_run_id`：本次 Agent 运行编号；
- `task_ref`：任务引用；
- `context_bundle_ref`：上下文工件引用；
- `allowed_tool_capabilities`：允许请求的工具能力；
- `allowed_output_types`：允许产生的工件类型；
- `policy_version`：权限策略版本；
- `prompt_template_version`：提示模板版本。

### AgentResult

Agent 只返回结构化候选结果，包括：

- 候选工件引用；
- 工具请求；
- 审批请求；
- 风险标记；
- 未解决问题；
- 建议；
- 置信度；
- 创建时间。

### AgentCapability

每个 Agent 都声明：

- 支持的任务类型；
- 可请求的工具能力；
- 可输出的工件类型；
- 禁止操作；
- 是否可以修改全局状态。

## 4. 权限边界

所有 Agent 都不能直接：

- 修改 `current_stage`；
- 批准研究工件；
- 冻结数据；
- 生成或篡改正式统计结果；
- 发布论文或报告。

Agent 只能提出候选工件和 `ToolRequest`。工具请求必须由 Controller 接收，再交给对应 Operator 执行。

独立审稿 Agent 没有执行工具能力，只能返回审稿发现、修订请求和审稿建议。

## 5. 同时补充的协议模型

实现了以下 Phase 1 协议模型：

```text
ResearchContract
ResearchQuestion
Hypothesis
Estimand
CausalDAGRef
StudyProtocol
PreregisteredAnalysisPlan
AtomicClaim
```

其中 `PreregisteredAnalysisPlan` 具有以下约束：

- 默认状态是 `candidate`；
- `approved` 必须有 `approval_ref`；
- `frozen` 必须同时有 `approval_ref` 和 `frozen_at`；
- 未批准的计划不能直接成为冻结计划。

`AtomicClaim` 只能有一个 `claim_type`：

```text
LITERATURE
RESULT
METHOD
INTERPRETATION
SPECULATION
LIMITATION
```

因此不允许使用 `RESULT + INTERPRETATION` 这种复合类型。

## 6. 测试内容

新增测试文件：

```text
backend/tests/test_agents.py
backend/tests/test_controller_agents.py
```

测试覆盖：

1. 六个 Agent 都可以正常运行；
2. Agent 都返回结构化 `AgentResult`；
3. Agent 只输出 Controller 授权的工件类型；
4. AgentResult 拒绝 `new_current_stage` 等越权字段；
5. Agent Capability 声明只读全局状态；
6. Reviewer 没有执行工具权限；
7. 预注册分析计划必须先审批才能冻结；
8. AtomicClaim 只能使用一个主张类型。

Controller 集成测试还覆盖：

9. Controller 默认注册且只注册六类 Agent；
10. AgentResult 必须经过 Controller 校验；
11. 导师规划结果会生成 `ApprovalRequest`；
12. 规划流程会停在 `WAITING_HUMAN`；
13. 只有 Controller 审批方法可以推进到 `SCOPED`；
14. 错误的审批请求和越权工件会被拒绝。

## 6.1 Controller 最小纵向闭环

当前已经实现：

```text
PlanningRequest
→ AgentRegistry
→ MentorPlanningAgent
→ AgentDispatcher
→ validate_agent_result
→ ApprovalRequest
→ WAITING_HUMAN
→ Controller 审批
→ SCOPED
```

这个闭环仍然使用确定性脚手架，不调用真实大模型。`candidate_artifact_refs` 只是候选工件引用，不能当作正式批准的研究协议。

## 7. 实际测试结果

在仓库根目录执行：

```powershell
python -m pytest backend/tests/test_agents.py -q
```

结果：

```text
11 passed
```

完整工程检查结果：

```text
ruff check backend/src backend/tests  → All checks passed
mypy backend/src                      → Success: no issues found
pytest backend/tests -q               → 35 passed, 10 skipped
python -m compileall backend/src      → 通过
stem_sci 导入检查                    → 通过
```

其中 Agent 与 Controller 集成测试合计 17 项通过。跳过的 10 项仍是项目早期预留的不变量测试，主要对应完整数据链、LangGraph 工作流和后续 Phase 1 模型，不代表本次 Agent 或 Controller 测试失败。

## 8. 手动运行示例

在 PowerShell 中执行：

```powershell
cd "D:\揭榜挂帅-psy"
$env:PYTHONPATH="D:\揭榜挂帅-psy\backend\src"
```

然后可以运行一个导师规划 Agent：

```powershell
@'
from stem_sci.agents import MentorPlanningAgent, AgentInput

agent = MentorPlanningAgent()
request = AgentInput(
    agent_run_id="demo-run-001",
    task_ref="physics-stem-demo",
    context_bundle_ref="context-demo",
    allowed_tool_capabilities=["literature_search_request"],
    allowed_output_types=list(agent.allowed_output_types),
    policy_version="policy-v1",
    prompt_template_version="prompt-v1",
)

print(agent.run(request).model_dump_json(indent=2))
'@ | python
```

输出中的 `candidate_artifact_refs` 是候选工件引用，例如：

```text
candidate://mentor_planning/physics-stem-demo/ResearchContractCandidate
candidate://mentor_planning/physics-stem-demo/ResearchQuestionTree
```

这些引用证明 Agent 按角色返回了候选结果，但它们还不是正式批准工件。

也可以直接测试 Controller：

```powershell
@'
from stem_sci.controller import PlanningRequest, ResearchController

run = ResearchController().start_planning(
    PlanningRequest(
        project_id="physics-ai-demo",
        research_intent="研究生成式 AI 分层支架对师范生 Python 物理建模迁移能力的影响",
        run_id="planning-run-001",
    )
)

print(run.workflow_state.current_stage)
print(run.approval_request.request_id)
print(len(run.agent_result.candidate_artifact_refs))
'@ | python
```

预期输出：

```text
WAITING_HUMAN
approval-planning-run-001
8
```

## 9. 当前尚未实现的内容

本次明确没有实现：

- 真实大模型调用；
- 真实文献检索和 PDF 检索；
- LangGraph 运行图；
- ContextBundle 的真实 Agent 集成；
- SPSS/Python 统计执行；
- 真实数据冻结；
- 多 Agent 动态协作和辩论；
- 论文自动生成和正式发布。

当前 Controller 只实现了一个最小内存闭环，还不是完整项目状态机。因此，当前结果应称为：

> 六类 Agent 的 Phase 1 结构化契约与权限脚手架。

不能称为“六个 Agent 已经可以自动完成科研项目”。

## 10. 下一阶段建议

下一步建议按以下顺序推进：

1. 接入 ContextBundle，只允许 Agent 读取引用化上下文；
2. 把 `EvidenceReviewAgent` 接到现有知识库检索服务；
3. 将 Controller 状态和审批记录接入持久化 Store；
4. 实现最小 Mock Agent 多步协作闭环；
5. 实现 Research Protocol Compiler 的候选协议输出；
6. 最后再接入真实模型和多轮 Reviewer 修订。
