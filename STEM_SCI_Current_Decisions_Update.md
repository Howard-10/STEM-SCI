# STEM-SCI 当前最终决策更新文档

> 文件用途：将本文件交给 Codex，作为现阶段项目设计和后续开发的最新决策依据。  
> 文档性质：架构决策增量更新。  
> 优先级：本文件中的决策高于此前对话中的零散建议；与既有设计文档不冲突的内容继续保留。  
> 当前要求：先更新技术方案、目录和数据结构设计，不立即一次性实现全部业务模块。

---

# 0. Codex 当前进度确认

Codex 当前已经完成并理解以下设计修正，这些内容继续保留：

1. 正式 `AnalysisPlan` 必须在 `FrozenDataset` 创建之后审批。
2. 数据采用三层版本：`RawDataset`、`ProcessedDataset`、`FrozenDataset`。
3. 数据分析 Agent 只能提出数据处理建议，不能自行修改或冻结数据。
4. `FrozenDataset` 只能由 Controller 调用确定性冻结服务创建。
5. 所有正式 `ExecutionRun` 只能读取 `FrozenDataset`。
6. 已区分 `SPSS_PYTHON_DUAL` 与 `PYTHON_ONLY`。
7. 已定义 `DataProcessingPlan`、`DataFreezeRecord`、`CodeSpecification`、`CodeArtifact`、`ExecutionRun`、`StatisticalResultCard`。
8. 已定义 `LITERATURE`、`RESULT`、`METHOD`、`INTERPRETATION`、`SPECULATION`、`LIMITATION` 六类科研主张。
9. 已形成主要工件质量 Gate。
10. 已明确 Coding Sandbox 的安全限制。
11. 已建立数据、分析、文献、竞赛验证等基础目录规划。
12. 已明确 Controller 是唯一有权改变 `current_stage` 的组件。

以上设计不推翻，后续方案在此基础上扩展。

---

# 1. 项目最终定位

## 1.1 正式名称

**STEM-SCI：面向教育学一流学科建设的可追溯科研智能体系统**

副标题：

> **聚焦 STEM 编程教育实验的研究协议编译、教学实验评价、科研数据分析与证据追溯**

## 1.2 学科定位

```text
一级学科：教育学
垂直方向：STEM 教育
具体场景：STEM 编程教育实验研究
核心用户：高校教育学教师、教育技术研究者、硕博研究生、STEM 教师教育团队
```

## 1.3 一句话定位

> STEM-SCI 不是自动写论文工具，而是将教育研究者的自然语言研究构想编译为可执行、可审批、可验证、可复现和可追溯的 STEM 教育科研流程，并将文献、研究协议、教学干预、学生代码、数据、分析代码、统计结果和论文主张连接起来。

## 1.4 产品边界

本系统不是：

- 普通教育学问答机器人；
- 自动代写论文系统；
- 六个 Agent 自由聊天系统；
- Agent 自行决定研究结论的系统；
- 大模型直接生成统计数字的系统；
- 仅用于自动批改代码的平台；
- 仅用于文献综述的平台；
- 完全无人监督的“自动科学家”。

---

# 2. 项目需要解决的核心问题

1. 自然语言研究想法难以转化为规范、可执行的研究方案。
2. 文献证据、研究问题和研究设计之间缺少结构化连接。
3. STEM 编程任务、教学提示、评价 Rubric 和实验变量容易脱节。
4. 学生在 AI 帮助下完成代码，不代表真正形成独立能力。
5. 原始数据、处理数据和正式分析数据版本混乱。
6. 分析计划、统计代码和实际执行结果可能不一致。
7. SPSS、Python、代码工具和论文写作工具之间彼此割裂。
8. AI 生成的引用、数字和因果表述存在科研诚信风险。
9. 论文中的结论难以追溯至真实文献、数据和执行记录。
10. 多 Agent 工作流容易出现越权、无限返工和不可解释路由。

系统核心价值：

> **提高教育科研过程的规范性、可信性、可执行性和可复现性。**

---

# 3. 最终确定的五个核心创新

后续技术文档、PPT 和答辩统一围绕以下五个核心创新展开。

## 3.1 教育研究协议编译器

名称：

```text
Research Protocol Compiler
```

将自然语言研究构想编译为：

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
AnalysisPlan
CodeSpecification
QualityGatePlan
PreregistrationSnapshot
```

普通大模型主要生成文字；STEM-SCI 生成可以执行、审批和验证的研究协议。

## 3.2 科研单元测试与工件质量控制

名称：

```text
Rubric-driven Research Unit Testing
```

每个科研工件必须运行对应的可执行科研检查，而不是只判断 Agent 是否给出了内容。

统一结果：

```python
class ResearchTestResult:
    test_id: str
    artifact_id: str
    status: str          # PASS / FAIL / WARNING / NOT_APPLICABLE
    severity: str        # LOW / MEDIUM / HIGH / CRITICAL
    evidence_refs: list[str]
    failure_reason: str | None
    repair_action: str | None
    executed_at: str
```

## 3.3 Agent—证据—执行—主张全链路溯源图

名称：

```text
Agent–Evidence–Execution–Claim Provenance Graph
```

追溯链覆盖：

```text
用户输入
→ Controller 路由决策
→ AgentRun
→ Agent 输入与输出
→ Reviewer 意见
→ 人工审批
→ 工件版本
→ 文献证据
→ 教学任务
→ 学生代码
→ FrozenDataset
→ CodeArtifact
→ ExecutionRun
→ StatisticalResultCard
→ ClaimEvidenceMap
→ 论文具体句子
```

## 3.4 风险与不确定性感知的动态科研流程控制

名称：

```text
Risk-aware Research Orchestration Engine
```

控制依据：

```text
Completeness
EvidenceSupport
MethodRisk
CitationRisk
PedagogyRisk
PrivacyRisk
Reproducibility
Uncertainty
HumanImpact
BudgetUsage
```

系统采用：

> 硬规则优先、结构化评分辅助、高风险人工兜底。

## 3.5 教学有效性与科研有效性双闭环

教学闭环：

```text
学生代码
→ 安全执行
→ 自动测试
→ 错误诊断
→ 分层提示
→ Feedback Firewall
→ 学生修改
→ 无 AI 迁移任务
→ 提示依赖与独立能力评价
```

科研闭环：

```text
AnalysisPlan
→ CodeSpecification
→ Codex 生成代码
→ 方法与安全审查
→ SPSS 主分析
→ Python 独立复核
→ 一致性检查
→ StatisticalResultCard
→ ClaimEvidenceMap
→ 论文主张审查
```

---

# 4. 最终总体架构

```text
用户科研工作台
        ↓
Research Protocol Compiler
        ↓
Risk-aware Research Controller
        ↓
Research Unit Test & Gate Engine
        ↓
六类专业 Agent
        ↓
专业 Subgraph
        ↓
Operator Registry
        ↓
GraphRAG / Memory / Stores / Sandbox
        ↓
Agent–Evidence–Execution–Claim Provenance Graph
```

## 4.1 六类 Agent

继续保留：

1. 导师规划 Agent；
2. 证据综述 Agent；
3. 研究设计 Agent；
4. 科研计算与数据分析 Agent；
5. 论文写作 Agent；
6. 独立审稿 Agent。

所有 Agent 只能返回结构化 `AgentResult`，不得：

- 直接修改 `current_stage`；
- 直接修改人工审批结果；
- 直接冻结数据；
- 直接覆盖正式工件；
- 直接发布结果；
- 直接改写真实统计数字。

## 4.2 六个专业 Subgraph

```text
LiteratureSubgraph
StudyDesignSubgraph
STEMExperimentSubgraph
AnalysisSubgraph
WritingSubgraph
ReproductionAuditSubgraph
```

## 4.3 Operator 层

Agent 负责推理，Operator 负责确定性操作。Controller 通过 Operator Registry 调用工具，不直接耦合具体实现。

建议 Operator：

```text
LiteratureSearchOperator
PaperScreeningOperator
PaperExtractionOperator
NoveltyCheckOperator
DataIngestionOperator
DataAuditOperator
DataProcessingOperator
DataFreezeOperator
LearnerCodeExecutionOperator
LearnerCodeEvaluationOperator
HintGenerationOperator
FeedbackEvaluationOperator
CodexOperator
SPSSOperator
PythonAnalysisOperator
ConsistencyCheckOperator
ProvenanceOperator
ArtifactExportOperator
ResearchUnitTestOperator
```

```python
class OperatorSpec:
    operator_id: str
    operator_version: str
    input_schema: str
    output_schema: str
    required_permissions: list[str]
    supported_artifact_types: list[str]
    estimated_cost: float
    timeout_seconds: int
    retry_policy: dict
    health_check_required: bool
```

```python
class OperatorRun:
    operator_run_id: str
    operator_id: str
    operator_version: str
    input_artifact_refs: list[str]
    output_artifact_refs: list[str]
    started_at: str
    finished_at: str
    status: str
    error_ref: str | None
    environment_ref: str | None
```

---

# 5. 高级流程控制最终设计

## 5.1 主状态机

顶层状态保持简洁：

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

复杂步骤放进 Subgraph，不全部升级为顶层状态。

## 5.2 GateResult

```python
class GateResult:
    gate_id: str
    gate_version: str
    artifact_id: str

    completeness_score: float
    evidence_support_score: float
    method_validity_score: float
    reproducibility_score: float
    uncertainty_score: float
    human_impact_score: float

    research_test_results: list[str]
    missing_fields: list[str]
    risk_flags: list[str]

    decision: str
    next_action: str | None
    created_at: str
```

允许的决策：

```text
PASS
PASS_WITH_WARNING
REWORK
BLOCKED
WAITING_HUMAN
FAILED
```

## 5.3 RiskProfile

```python
class RiskProfile:
    artifact_id: str
    method_risk: float
    citation_risk: float
    pedagogy_risk: float
    privacy_risk: float
    reproducibility_risk: float
    causal_overclaim_risk: float
    answer_leakage_risk: float
    overall_level: str
    triggered_rules: list[str]
```

## 5.4 RouteDecision

```python
class RouteDecision:
    decision_id: str
    current_stage: str
    artifact_ids: list[str]
    selected_route: str
    triggered_rules: list[str]
    risk_profile_ref: str | None
    gate_result_refs: list[str]
    budget_snapshot_ref: str | None
    model_suggestion: str | None
    final_decider: str       # controller | human
    policy_version: str
    created_at: str
```

## 5.5 BudgetState

```python
class BudgetState:
    max_llm_calls: int
    used_llm_calls: int
    max_retrieval_calls: int
    used_retrieval_calls: int
    max_code_retries: int
    used_code_retries: int
    max_review_rounds: int
    used_review_rounds: int
    max_execution_seconds: int
    used_execution_seconds: int
```

## 5.6 路由优先级

```text
第一优先：安全与科研诚信硬规则
第二优先：人工审批规则
第三优先：科研单元测试与 Gate
第四优先：风险评分与动态 Reviewer
第五优先：预算和资源策略
第六优先：模型建议
```

模型建议不得覆盖硬规则。

## 5.7 失败与重试

```text
第一次失败：
原 Agent 或 Operator 定向修复

第二次失败：
Controller 重新拆解任务或更换 Operator

第三次失败：
WAITING_HUMAN

缺少真实证据、真实数据、伦理条件或合法权限：
直接 BLOCKED
```

---

# 6. 科研单元测试最终设计

新增：

```text
src/verification/
├── models.py
├── rubric_registry.py
├── test_runner.py
├── question_tests.py
├── evidence_tests.py
├── protocol_tests.py
├── stem_task_tests.py
├── feedback_tests.py
├── data_tests.py
├── analysis_tests.py
├── result_tests.py
├── claim_tests.py
└── release_tests.py
```

## 6.1 ResearchQuestion 测试

```text
RQ-01 研究对象是否明确
RQ-02 干预与对照是否可操作
RQ-03 主要结果是否唯一
RQ-04 是否可被当前设计回答
RQ-05 是否存在不可识别的因果问题
RQ-06 是否有证据支持问题重要性
```

## 6.2 StudyProtocol 测试

```text
SP-01 研究对象与 ResearchContract 一致
SP-02 Treatment 和 Comparator 定义完整
SP-03 主要结果与 AnalysisPlan 一致
SP-04 干预可复现
SP-05 已识别教师、班级和任务混淆
SP-06 伦理和隐私条件完整
SP-07 样本量有 PowerAnalysis 依据
SP-08 研究设计与 Estimand 匹配
```

## 6.3 STEM 编程任务测试

```text
ST-01 任务知识点与教学目标一致
ST-02 数学、物理和编程难度可解释
ST-03 单元测试覆盖核心模型错误
ST-04 Rubric 不只评价代码能否运行
ST-05 隐藏测试未泄漏
ST-06 AI 提示不能直接给完整答案
ST-07 任务 A/B 难度具有等值证据
ST-08 存在无 AI 迁移任务
```

## 6.4 AnalysisPlan 测试

```text
AP-01 每项分析对应明确 RQ 或假设
AP-02 主要分析与探索性分析已区分
AP-03 缺失值策略预先确定
AP-04 异常值策略预先确定
AP-05 模型与 Estimand 匹配
AP-06 效应量和置信区间要求完整
AP-07 多重比较策略完整
AP-08 替代模型触发条件明确
AP-09 变量均存在于 FrozenDataset Schema
```

## 6.5 StatisticalResultCard 测试

```text
SR-01 数据哈希一致
SR-02 代码哈希一致
SR-03 案例集合一致
SR-04 模型设置一致
SR-05 关键数值通过容差
SR-06 假设检查完整
SR-07 效应量存在
SR-08 置信区间存在
SR-09 解释未超过研究设计边界
```

## 6.6 Claim 测试

```text
CL-01 LITERATURE 主张有文献证据
CL-02 RESULT 主张有 StatisticalResultCard
CL-03 METHOD 主张有批准后的协议
CL-04 INTERPRETATION 同时关联结果与理论
CL-05 SPECULATION 明确标记
CL-06 数字与结果卡一致
CL-07 因果强度不超过设计等级
CL-08 未使用 model_generated_unverified 支持正式结论
```

---

# 7. STEM 编程实验模块最终决策

## 7.1 两类代码严格分离

```text
LearnerCodeArtifact
ResearchCodeArtifact
```

分别使用：

```text
LearnerCodeSandbox
ResearchCodeSandbox
```

## 7.2 主 Demo

> **生成式 AI 分层支架对师范生 Python 物理建模表现、无辅助迁移能力和提示依赖的影响：一项随机交叉实验。**

任务：

```text
任务 A：Python 抛体运动建模
任务 B：Python 弹簧振子建模
任务 C：无 AI 迁移任务
```

条件：

```text
组 1：
任务 A 使用 AI 支架
任务 B 使用静态提示

组 2：
任务 A 使用静态提示
任务 B 使用 AI 支架
```

任务顺序随机平衡。

## 7.3 新增 STEM 实验工件

```text
ProgrammingTaskSpecification
InterventionProtocol
HintPolicy
CodeRubric
UnitTestSpecification
TaskEquivalenceReport
TeachingFidelityChecklist
InterventionFidelityReport
LearnerCodeArtifact
LearnerCodeEvaluationRun
LearningProcessEvent
HintDependencyReport
IndependentTransferReport
```

## 7.4 学生代码评价维度

```text
代码运行正确性
物理模型正确性
数值计算准确性
代码结构与可读性
调试过程
错误类型
提示使用情况
解释能力
无 AI 迁移能力
提示依赖程度
```

## 7.5 过程事件

```text
TASK_OPEN
CODE_EDIT
CODE_RUN
TEST_FAIL
TEST_PASS
HINT_REQUEST
HINT_SHOWN
HINT_ACCEPTED
SUBMISSION
TASK_CLOSE
```

保存：

```text
匿名学生 ID
session_id
task_id
timestamp
代码版本
提示级别
错误类型
相关工件引用
```

---

# 8. 教学反馈防火墙

流程：

```text
学生代码
→ 错误诊断
→ 生成候选提示
→ Feedback Firewall
→ PASS：发送学生
→ FAIL：重新生成或降低提示级别
```

检查：

```text
Correctness
PedagogicalValue
AnswerLeakageRisk
HallucinationRisk
LevelAppropriateness
SafetyRisk
Clarity
```

提示阶梯：

```text
L1 反思性问题
L2 概念提示
L3 错误区域定位
L4 局部伪代码
L5 最小代码片段
```

默认从最低提示等级开始。

禁止：

- 直接提供完整答案；
- 泄露隐藏测试；
- 使用超出课程范围的 API；
- 要求学生提供隐私信息；
- 提供危险系统命令。

```python
class FeedbackEvaluation:
    feedback_id: str
    correctness_score: float
    pedagogical_value_score: float
    answer_leakage_risk: float
    hallucination_risk: float
    level_appropriateness_score: float
    safety_risk: float
    decision: str
    reasons: list[str]
```

---

# 9. 研究设计候选搜索

新增：

```text
Bounded Research Design Search
```

只在数据收集和正式预注册之前使用。

允许：

- 研究问题候选；
- 实验设计候选；
- STEM 任务候选；
- AI 提示策略候选；
- 分析方案候选。

禁止：

- 根据显著性修改分析；
- 修改冻结数据；
- 自动覆盖批准后的 AnalysisPlan；
- 自动发布结果。

候选评分：

```text
InternalValidity
ExternalValidity
Feasibility
EthicsRisk
StatisticalPower
SampleRequirement
DataComplexity
RQAlignment
```

流程：

```text
生成 3 个候选
→ Method Reviewer 评价
→ Controller 保留前 2 个
→ 研究者选择
```

---

# 10. 数据和统计分析决策

## 10.1 正式数据流程

```text
AnalysisPlan 草案

RawDataset
→ DataAuditReport
→ DataProcessingPlan 人工批准
→ ProcessedDataset
→ Controller 调用 DataFreezeOperator
→ FrozenDataset
→ AnalysisPlan 正式批准
→ CodeSpecification
→ Codex 生成代码
→ CodeReviewGate
→ SPSS / Python 执行
→ ResultConsistencyReport
→ StatisticalResultCard
```

## 10.2 SPSS 降级策略

```text
开发和 MVP：
PYTHON_ONLY

完整版本且 SPSS 可用：
SPSS_PYTHON_DUAL

SPSS 不可用：
PYTHON_ONLY
```

界面和结果卡必须明确显示模式，禁止把 `PYTHON_ONLY` 宣传为双引擎验证。

## 10.3 一致性检查四层

输入一致性：

```text
dataset_sha256
案例 ID 集合
样本量
变量类型
```

模型一致性：

```text
设计矩阵
参考组
缺失值策略
平方和类型
对比编码
```

数值一致性：

```text
系数
标准误
自由度
统计量
p 值
效应量
置信区间
```

结论一致性：

```text
方向
显著性结论
效应量解释
```

先验证输入和模型一致，再比较数值。

## 10.4 核验状态分离

文献核验状态：

```text
demo_seed
model_generated_unverified
source_verified
human_verified
```

执行核验状态：

```text
generated
execution_verified
cross_engine_verified
human_approved
```

---

# 11. 细粒度科研溯源

```python
class AgentRunRecord:
    agent_run_id: str
    agent_id: str
    agent_version: str
    prompt_template_version: str
    input_artifact_refs: list[str]
    output_artifact_refs: list[str]
    tool_run_refs: list[str]
    reviewer_feedback_refs: list[str]
    route_decision_ref: str
    started_at: str
    finished_at: str
```

主要图谱边：

```text
GENERATED
USED
DERIVED_FROM
REVIEWED_BY
APPROVED_BY
CAUSED_REVISION_OF
EXECUTED_WITH
SUPPORTED_BY
CONTRADICTED_BY
REPORTED_IN
```

论文主张必须能够回到：

```text
ResearchQuestion
AnalysisPlan
FrozenDataset
CodeArtifact
ExecutionRun
StatisticalResultCard
HumanApproval
```

新增 `WorkflowSignature`，由以下内容的哈希组合生成：

```text
研究协议哈希
数据哈希
代码哈希
环境哈希
执行输出哈希
```

---

# 12. 教育研究复现审计模式

新增第二个应用模式：

```text
Reproduction Audit Mode
```

输入：

```text
论文 PDF
数据文件
Python / R 代码
SPSS Syntax
补充材料
```

检查：

```text
论文样本量是否与数据一致
变量定义是否一致
代码是否可以执行
表格数字是否可以复现
效应量是否可重新计算
排除规则是否完整
正文是否选择性报告
结论是否超过设计与结果
```

输出：

```text
ReproductionAuditReport
```

状态：

```text
FULLY_REPRODUCIBLE
PARTIALLY_REPRODUCIBLE
NOT_REPRODUCIBLE
INSUFFICIENT_MATERIALS
```

与主科研流程共用：

- ArtifactStore；
- ExecutionStore；
- Codex；
- Python；
- SPSS；
- StatisticalResultCard；
- ClaimEvidenceMap；
- Reviewer；
- Provenance Graph。

---

# 13. GraphRAG 和知识库决策

## 13.1 MVP

第一版统一使用一个多语言嵌入模型和固定维度。

禁止将不同维度向量放入同一个 Chroma Collection。

## 13.2 后续双 Collection

```text
collection_model_a
collection_model_b
```

分别检索后：

```text
分数归一化
→ RRF 融合
→ MMR 重排
```

## 13.3 知识资产

```text
STEM 教育文献库
教育理论库
研究方法库
量表库
研究协议模板库
编程任务库
Rubric 库
学生错误模式库
科研单元测试库
统计分析模板库
可复现研究案例库
```

---

# 14. 目录结构增量更新

在现有目录基础上新增：

```text
src/
├── research_protocol/
│   ├── compiler.py
│   ├── models.py
│   ├── feasibility.py
│   ├── estimand.py
│   ├── causal_dag.py
│   ├── preregistration.py
│   └── candidate_search.py
│
├── operators/
│   ├── registry.py
│   ├── models.py
│   ├── literature/
│   ├── research_data/
│   ├── learner_code/
│   ├── feedback/
│   ├── coding/
│   ├── statistics/
│   ├── provenance/
│   └── verification/
│
├── controller/
│   ├── policy/
│   │   ├── policy_engine.py
│   │   ├── rule_policy.py
│   │   ├── policy_versions.py
│   │   └── route_decision.py
│   ├── risk/
│   │   ├── risk_engine.py
│   │   ├── method_risk.py
│   │   ├── citation_risk.py
│   │   ├── pedagogy_risk.py
│   │   ├── privacy_risk.py
│   │   └── reproducibility_risk.py
│   ├── budget/
│   │   ├── budget_manager.py
│   │   └── resource_tracker.py
│   └── subgraphs/
│       ├── literature_graph.py
│       ├── study_design_graph.py
│       ├── stem_experiment_graph.py
│       ├── analysis_graph.py
│       ├── writing_graph.py
│       └── reproduction_audit_graph.py
│
├── learner_code/
│   ├── models.py
│   ├── ingestion.py
│   ├── sandbox.py
│   ├── test_runner.py
│   ├── rubric_engine.py
│   ├── code_metrics.py
│   ├── error_classifier.py
│   ├── process_events.py
│   └── feature_exporter.py
│
├── feedback/
│   ├── models.py
│   ├── hint_generator.py
│   ├── firewall.py
│   ├── correctness_checker.py
│   ├── leakage_detector.py
│   ├── pedagogy_checker.py
│   └── safety_checker.py
│
├── verification/
│   ├── models.py
│   ├── rubric_registry.py
│   ├── test_runner.py
│   ├── question_tests.py
│   ├── evidence_tests.py
│   ├── protocol_tests.py
│   ├── stem_task_tests.py
│   ├── feedback_tests.py
│   ├── data_tests.py
│   ├── analysis_tests.py
│   ├── result_tests.py
│   ├── claim_tests.py
│   └── release_tests.py
│
├── provenance/
│   ├── models.py
│   ├── graph_builder.py
│   ├── agent_run_store.py
│   ├── lineage_query.py
│   └── workflow_signature.py
│
└── reproduction_audit/
    ├── models.py
    ├── material_ingestion.py
    ├── manuscript_parser.py
    ├── replication_runner.py
    ├── consistency_auditor.py
    └── report_builder.py
```

现有 `core`、`graph_rag`、`memory`、`artifacts`、`research_data`、`coding`、`statistics`、`executors`、`evaluation`、`api`、`utils` 继续保留。

Codex 更新目录时必须处理职责重叠：

- `operators/` 负责统一调用与运行接口；
- `coding/`、`statistics/` 保留领域实现；
- `verification/` 负责可执行科研测试；
- `controller/gates/` 负责根据测试结果作流程决策；
- `provenance/` 负责关系建模与查询；
- `artifacts/provenance.py` 可改为底层血缘写入适配或并入新模块；
- `feedback/` 负责提示生成和防火墙；
- `learner_code/` 负责学生代码运行、评分和特征提取；
- `research_protocol/` 负责协议编译；
- `design_agent.py` 负责基于证据提出设计候选，不负责确定性编译和审批。

---

# 15. ResearchState 增量修改

```python
class ResearchState(TypedDict):
    current_stage: str
    task_status: str

    task_ledger: TaskLedger
    progress_ledger: ProgressLedger
    evidence_ledger: list[EvidenceItem]

    artifact_refs: list[ArtifactRef]
    data_asset_refs: list[DataAssetRef]
    execution_run_refs: list[ExecutionRunRef]

    protocol_refs: list[str]
    research_test_result_refs: list[str]
    risk_profile_refs: list[str]
    route_decision_refs: list[str]
    agent_run_refs: list[str]
    approval_request_refs: list[str]

    budget_state: BudgetState

    recent_rounds: list[dict]
    short_memory_summary: ShortMemorySummary | None
    long_memory_refs: list[str]

    risk_flags: list[RiskEvent]
    error_log: list[ErrorEvent]
```

禁止将以下内容直接放入 State：

- PDF 全文；
- 完整数据；
- 学生代码正文；
- 科研分析代码正文；
- SPSS 输出；
- 图像；
- 大型运行日志；
- 完整 Agent 对话记录。

---

# 16. 实施路线最终决策

## Phase 0：同步设计文档

Codex 下一步先完成：

1. 合并本文件决策到技术架构文档；
2. 更新完整目录树；
3. 更新核心数据结构；
4. 更新主状态机和 Subgraph；
5. 更新 MVP 和阶段计划；
6. 输出修改差异；
7. 暂不批量生成全部业务代码。

## Phase 1：核心基础和状态安全

实现：

```text
Core Models
ResearchState
ArtifactRef
AgentResult
OperatorSpec
ResearchTestResult
RiskProfile
RouteDecision
BudgetState
Reducer
Controller Merger
ApprovalRequest
```

验收：

- Agent 不能改变阶段；
- 并行写入不覆盖；
- 大对象不进入 State；
- 每次路由有记录。

## Phase 2：最小真实闭环

```text
上传学生代码
→ LearnerCodeSandbox
→ 自动测试与评分
→ 合并学习数据
→ Raw/Processed/Frozen 数据链路
→ AnalysisPlan
→ PYTHON_ONLY 分析
→ StatisticalResultCard
→ ClaimEvidenceMap
→ 可追溯结果段
```

## Phase 3：科研单元测试和 Gate

实现基础 Gate、科研单元测试注册表及 REWORK/BLOCKED 路由。

## Phase 4：STEM 实验和教学反馈

实现任务、Rubric、Feedback Firewall、过程日志、迁移与依赖评价。

## Phase 5：文献证据和研究协议编译

实现 Research Protocol Compiler、PaperCard、EvidenceMatrix、候选设计、Estimand、CausalDAG、PowerAnalysis、预注册。

## Phase 6：Codex、SPSS 和双引擎分析

实现 CodingProvider、CodexProvider、SPSSAdapter、PythonAdapter、ConsistencyChecker。

## Phase 7：动态流程控制和高级 Reviewer

实现 Risk Engine、动态路由、预算管理和多 Reviewer。

## Phase 8：写作、复现审计和产品化

实现论文生成、复现审计、溯源界面、WorkflowSignature、用户测试和竞赛 Demo。

---

# 17. 竞赛验证决策

至少准备三个黄金案例。

## 17.1 文献证据链

指标：

```text
筛选 Precision
筛选 Recall
字段抽取准确率
原文定位率
虚假引用率
```

## 17.2 学生代码评价

指标：

```text
自动测试准确率
错误分类准确率
教师评分一致性
答案泄漏率
无 AI 迁移表现
```

## 17.3 统计与写作复现

指标：

```text
代码执行成功率
结果数值一致率
效应量准确率
论文数字一致率
因果过度表述率
```

## 17.4 工作流消融

比较：

```text
单 Agent
固定六 Agent
固定多 Agent + Gate
风险感知动态工作流
```

指标：

```text
任务成功率
错误检出率
返工次数
模型调用次数
平均耗时
平均成本
虚假引用率
统计错误率
```

---

# 18. 当前默认技术策略

## 18.1 ArtifactStore

MVP：

```text
文件：本地项目隔离目录
元数据：PostgreSQL 或轻量数据库
引用：storage_uri + version + SHA256
```

## 18.2 CodingProvider

第一阶段：

```text
MockCodingProvider
ManualCodingProvider
```

接口稳定后再接入真实 CodexProvider。

## 18.3 统计模式

MVP：

```text
PYTHON_ONLY
```

完整版本：

```text
SPSS_PYTHON_DUAL
```

## 18.4 嵌入模型

MVP：

```text
统一多语言嵌入模型
```

## 18.5 工作流优化

运行时：

```text
固定安全规则 + 风险动态路由
```

开发期：

```text
根据历史日志离线优化阈值和路由策略
```

暂不允许在线自动改写正式科研流程。

---

# 19. 仍未最终决定的问题

Codex 不应自行假设以下事项。

## 19.1 阻塞真实部署

- 可用于演示的合法脱敏数据来源；
- SPSS 许可证、安装节点和运行方式；
- 真实 CodexProvider 的鉴权方式；
- 正式 ArtifactStore 后端；
- 人工审批角色和权限体系。

## 19.2 需要实验确定

- 风险评分阈值；
- Gate 通过阈值；
- SPSS/Python 数值容差；
- Rubric 权重；
- AnswerLeakageRisk 阈值；
- Reviewer 触发条件；
- 任务 A/B 等值标准。

## 19.3 后续扩展

- R 语言；
- `.sav` 原生导入；
- 双 Collection 融合；
- Neo4j 深层推理；
- 多模态课堂视频；
- 大规模用户测试；
- 机构级权限；
- 自动投稿和期刊适配。

---

# 20. 当前明确不实施的内容

第一版和比赛前期暂不实施：

- 完全自主科研；
- 在线 MCTS 自动修改正式研究协议；
- Agent 自行修改冻结 AnalysisPlan；
- Agent 根据显著性结果选择方法；
- 无限多 Agent 辩论；
- 自动生成虚假实验数据；
- 自动投稿；
- 直接控制 SPSS 图形界面；
- 在主服务进程运行不可信学生代码；
- 将完整文件塞入 ResearchState；
- 将 Codex 设为独立科研决策 Agent。

---

# 21. Codex 下一步任务

收到本文件后，先不要批量实现全部模块。

## Task 1：输出设计差异

比较当前设计和本决策文档，分为：

```text
保留
修改
新增
删除
延后
```

## Task 2：更新完整架构文档

加入：

- 最终项目定位；
- 五个核心创新；
- Research Protocol Compiler；
- Operator Registry；
- Research Unit Testing；
- Provenance Graph；
- Feedback Firewall；
- Reproduction Audit；
- Risk-aware Controller；
- 新实施路线。

## Task 3：更新数据结构

补充：

```text
OperatorSpec
OperatorRun
ResearchTestResult
RiskProfile
RouteDecision
BudgetState
AgentRunRecord
FeedbackEvaluation
LearnerCodeArtifact
LearnerCodeEvaluationRun
LearningProcessEvent
TaskEquivalenceReport
InterventionFidelityReport
ReproductionAuditReport
```

## Task 4：更新目录树并消除职责重复

重点检查：

- `operators/` 与 `coding/`、`statistics/`；
- `provenance/` 与 `artifacts/provenance.py`；
- `verification/` 与 `controller/gates/`；
- `feedback/` 与 `learner_code/`；
- `research_protocol/` 与 `design_agent.py`。

## Task 5：更新 Phase 0—Phase 8

每个阶段写明：

- 输入；
- 输出；
- 依赖；
- 验收标准；
- 风险；
- 是否允许 Mock。

## Task 6：停止等待确认

完成设计同步后停止，不开始大规模编码，等待负责人确认目录、数据结构和 Phase 1 范围。

---

# 22. 最终决策摘要

当前项目最终由以下部分组成：

```text
教育学垂类 GraphRAG
+
Research Protocol Compiler
+
六类专业 Agent
+
确定性 Operator Registry
+
风险感知动态流程控制
+
科研单元测试与工件 Gate
+
STEM 编程任务与学生代码评价
+
教学 Feedback Firewall
+
Raw / Processed / Frozen 数据链
+
Codex—SPSS—Python 可复现分析
+
Agent—证据—执行—主张溯源图
+
教育研究复现审计
```

最终核心表述：

> STEM-SCI 面向教育学一流学科建设，聚焦 STEM 编程教育实验研究，将研究者的自然语言构想编译为文献检索、实验设计、编程任务、教学支架、数据采集和统计分析等可执行科研协议。系统使用风险与不确定性感知的动态流程控制协调六类专业 Agent 与确定性 Operator，并通过科研单元测试、学生代码评价、教学反馈防火墙、Codex—SPSS—Python 可复现分析和全链路科研溯源，对教育科研全过程实施质量控制，最终形成从文献证据和学生学习过程到统计结果与论文主张的可追溯闭环。
