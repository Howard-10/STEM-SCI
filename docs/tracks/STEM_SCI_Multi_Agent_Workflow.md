# STEM-SCI 多 Agent 协作流程与输入输出设计

## 1. 系统总体思想

STEM-SCI 不采用传统流水线式 Agent 架构，而采用 **Controller 驱动的多 Agent 动态协作模式**。

传统方式：

```text
研究规划 Agent
        ↓
证据检索 Agent
        ↓
研究设计 Agent
        ↓
数据分析 Agent
        ↓
论文写作 Agent
        ↓
审稿 Agent
```

该方式存在以下问题：

1. 前序错误难以及时修正；
2. 科研过程中的反复修改无法充分表达；
3. Agent 之间缺少统一状态与权限约束；
4. 难以保证科研过程可追溯、可审计和可恢复。

因此，STEM-SCI 采用：

```text
ResearchState
        ↓
Research Controller
        ↓
多 Agent 动态协作
        ↓
Evidence / Protocol / Data / Result 更新
        ↓
ResearchState 更新
        ↓
下一轮动态调度
```

核心原则：

- Agent 负责专业推理；
- Controller 负责流程调度与状态治理；
- Operator 负责确定性执行；
- Human Approval 负责关键科研决策；
- 所有重要输出必须具备来源、版本与追溯引用。

---

## 2. 核心控制组件：Research Controller

### 2.1 定位

Research Controller 是整个科研智能体系统的流程控制中心。

它不负责生成专业科研结论，而是负责：

- 维护当前 `ResearchState`；
- 判断当前阶段缺少什么；
- 选择下一步调用哪个 Agent；
- 检查 Agent 权限；
- 处理 `ToolRequest` 与 `ApprovalRequest`；
- 调用 Operator；
- 执行 Gate 检查；
- 管理风险、预算、返工和阻塞；
- 生成 `RouteDecision`；
- 作为唯一可以推进 `current_stage` 的组件。

### 2.2 输入 Input

```text
ResearchState
```

主要包含：

```text
current_stage
task_status
evidence_refs
protocol_refs
artifact_refs
dataset_refs
execution_run_refs
approval_refs
review_refs
risk_flags
unresolved_questions
short_memory_summary
long_memory_refs
```

### 2.3 输出 Output

```text
RouteDecision
```

示例结构：

```json
{
  "next_agent": "research_design_agent",
  "reason": "已有证据充分，但当前缺少结构化研究协议",
  "required_context": [
    "research_contract",
    "evidence_matrix",
    "feasibility_report"
  ],
  "required_tools": [],
  "decision_scope": "TASK",
  "risk_level": "LOW"
}
```

### 2.4 主要路由规则

```text
研究范围不清
→ 导师规划 Agent

证据不足
→ 证据综述 Agent

研究设计不完整
→ 研究设计 Agent

数据、统计或结果有问题
→ 科研计算与数据分析 Agent

需要形成论文内容
→ 论文写作 Agent

需要质量审查
→ 独立审稿 Agent

需要真实检索、数据处理、代码或统计执行
→ Operator

需要正式确认
→ Human Approval
```

---

## 3. Agent 统一契约

六个 Agent 使用统一的输入输出模型。

### 3.1 AgentInput

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

### 3.2 AgentResult

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

### 3.3 禁止字段

AgentResult 不允许包含：

```text
new_current_stage
approved
freeze_dataset
official_result
publish
```

即 Agent 不能：

- 推进项目阶段；
- 批准研究工件；
- 冻结数据；
- 伪造正式结果；
- 直接发布论文或报告。

---

## 4. 导师规划 Agent

### 4.1 定位

导师规划 Agent 负责研究方向规划、范围界定和项目路线设计，可类比为科研导师、PI 或项目负责人。

### 4.2 核心任务

- 理解研究者需求；
- 拆解研究主题；
- 判断研究价值与创新空间；
- 明确研究对象、情境、干预和结果；
- 识别资源、时间和伦理约束；
- 形成研究问题树；
- 形成初步研究路线；
- 判断是否需要补充文献或缩小范围。

### 4.3 输入

```text
UserResearchIntent
ProjectProfile
ResourceConstraints
EthicsConstraints
InitialContextBundle
LongTermMemory
ExistingProjectDecisions
```

示例：

```text
研究主题：
分层渐退式生成式 AI 支架

研究对象：
职前教师

教学情境：
Python 物理建模

主要结果：
无 AI 迁移能力与提示依赖
```

### 4.4 处理过程

#### 第一步：意图解析

识别：

```text
研究对象
干预因素
对照条件
结果变量
研究情境
目标贡献
```

#### 第二步：可行性检查

检查：

```text
样本是否可获得
实验周期是否合理
任务难度是否可控
数据是否可采集
伦理风险是否可接受
统计分析是否可能实施
```

#### 第三步：研究范围与路线生成

形成：

```text
ResearchQuestionTree
ResearchScopeCandidate
ProjectRoadmap
LiteratureRequirementList
InitialRiskProfile
```

### 4.5 输出

```text
ResearchContractCandidate
FeasibilityReport
ResearchQuestionTree
ResearchScopeCandidate
ProjectRoadmap
LiteratureRequirementList
InitialRiskProfile
UnresolvedQuestionList
```

### 4.6 可能提出的 ToolRequest

```text
需要检索生成式 AI 支架相关理论
需要检索无 AI 迁移测量方式
需要检索提示依赖相关指标
```

### 4.7 重新调用条件

当出现以下情况时，Controller 重新调用导师规划 Agent：

```text
研究问题不可测量
研究范围过大
研究创新性不足
资源不足
伦理风险过高
研究设计无法实施
```

### 4.8 与其他 Agent 的动态关系

```text
导师规划 Agent → 证据综述 Agent
条件：需要理论和实证依据

证据综述 Agent → 导师规划 Agent
条件：发现研究空白变化或创新性不足

导师规划 Agent → 研究设计 Agent
条件：研究范围和路线已明确

研究设计 Agent → 导师规划 Agent
条件：方案不可行或超出资源
```

---

## 5. 证据综述 Agent

### 5.1 定位

证据综述 Agent 负责文献需求定义、证据组织、冲突识别和研究空白分析。

它不直接执行真实检索，而是通过 Controller 提交 `ToolRequest`，由 Literature Operator 或知识库检索服务完成执行。

### 5.2 核心任务

- 生成检索协议；
- 明确纳入与排除标准；
- 组织 `PaperCard`；
- 建立 `EvidenceMatrix`；
- 区分支持证据、对比证据和提及证据；
- 发现理论冲突、方法冲突和结果冲突；
- 判断证据是否充分；
- 形成研究空白；
- 向其他 Agent 提供可追溯证据。

### 5.3 输入

```text
ResearchContract
ResearchQuestionTree
LiteratureRequirementList
ContextBundle
ExistingEvidenceRefs
SearchConstraints
ProjectScope
```

知识来源包括：

```text
关键词检索
向量检索
图关系检索
公共知识库
项目私有知识库
用户个人知识库
```

### 5.4 处理过程

#### 第一步：检索协议生成

```text
查询主题
关键词组合
同义词
数据库范围
时间范围
纳入标准
排除标准
证据抽取字段
```

#### 第二步：提出 ToolRequest

```text
LiteratureSearchRequest
PaperScreeningRequest
PaperExtractionRequest
SourceVerificationRequest
```

调用链：

```text
证据综述 Agent
→ ToolRequest
→ Controller
→ Literature Operator
→ OperatorRun
→ Evidence 更新
→ ContextBundle 更新
```

#### 第三步：证据组织

形成：

```text
PaperCardCollection
EvidenceMatrixCandidate
EvidenceConflictMap
ResearchGapReport
EvidenceSufficiencyReport
```

### 5.5 输出

```text
SearchProtocolCandidate
InclusionExclusionCriteria
PaperCardCollection
EvidenceMatrixCandidate
EvidenceConflictMap
ResearchGapReport
EvidenceSufficiencyReport
LiteratureNeedUpdate
```

### 5.6 EvidenceMatrix 示例

| 研究主题 | 支持证据 | 对比证据 | 当前判断 |
|---|---|---|---|
| AI 提高训练表现 | 多篇研究支持 | 少量无显著结果 | 证据相对充分 |
| AI 提高无辅助迁移 | 证据有限 | 存在依赖风险 | 尚不充分 |
| 渐退支架降低依赖 | 理论支持较多 | 实证研究较少 | 明确研究空白 |

### 5.7 重新调用条件

```text
设计缺少文献支撑
论文引用不足
结果无法解释
审稿发现遗漏关键文献
讨论部分需要补充相反证据
```

### 5.8 与其他 Agent 的动态关系

```text
证据综述 Agent ↔ 导师规划 Agent
条件：研究空白变化、创新性不足

证据综述 Agent ↔ 研究设计 Agent
条件：设计需要文献支持或证据提出新的设计要求

证据综述 Agent ↔ 科研计算与数据分析 Agent
条件：异常结果需要外部解释

证据综述 Agent ↔ 论文写作 Agent
条件：引用缺失、Claim 缺少证据或讨论需补证据

独立审稿 Agent → 证据综述 Agent
条件：引用错误、证据不足或遗漏关键文献
```

---

## 6. 研究设计 Agent

### 6.1 定位

研究设计 Agent 负责把研究想法和证据转化为结构化、可执行、可审批的研究协议候选。

### 6.2 核心任务

- 生成研究问题和假设；
- 定义 Estimand；
- 构建 CausalDAG；
- 设计研究类型；
- 设计样本和分组；
- 定义变量、测量与时间点；
- 生成干预协议；
- 生成 STEM 编程任务；
- 生成数据采集 Schema；
- 生成预注册分析计划草案；
- 生成质量 Gate 计划。

### 6.3 输入

```text
ResearchContract
EvidenceMatrix
ResearchGapReport
FeasibilityReport
ResourceConstraints
EthicsConstraints
AvailableMeasures
ContextBundle
```

### 6.4 处理过程

#### 第一步：研究问题与假设

```text
ResearchQuestionCandidate
HypothesisCandidate
```

#### 第二步：因果目标定义

```text
Estimand
CausalDAG
```

Estimand 至少包括：

```text
Population
Treatment
Comparator
Outcome
Time
SummaryMeasure
```

#### 第三步：实验协议生成

```text
StudyProtocolCandidate
SamplingPlan
InterventionProtocol
MeasurementPlan
```

#### 第四步：STEM 编程专项设计

```text
ProgrammingTaskSpecification
HintPolicy
CodeRubric
UnitTestSpecification
```

示例任务：

```text
训练任务一：
抛体运动建模

训练任务二：
弹簧振子建模

无 AI 迁移任务：
单摆或冷却定律建模
```

#### 第五步：数据与分析规划

```text
DataCollectionSchema
PreregisteredAnalysisPlanDraft
QualityGatePlan
```

### 6.5 输出

```text
ResearchQuestionCandidate
HypothesisCandidate
Estimand
CausalDAG
StudyProtocolCandidate
SamplingPlan
InterventionProtocol
ProgrammingTaskSpecification
HintPolicy
CodeRubric
UnitTestSpecification
MeasurementPlan
DataCollectionSchema
PreregisteredAnalysisPlanDraft
QualityGatePlan
```

### 6.6 ApprovalRequest

```text
研究问题审批
主要结果变量审批
实验协议审批
伦理边界审批
预注册分析计划审批
```

### 6.7 重新调用条件

```text
协议字段缺失
逻辑不一致
研究设计缺乏证据
样本或变量不可获得
分析方法不可执行
数据结构不支持研究问题
伦理风险不可接受
```

### 6.8 与其他 Agent 的动态关系

```text
研究设计 Agent ↔ 证据综述 Agent
条件：设计缺少文献支撑

研究设计 Agent ↔ 导师规划 Agent
条件：方案不可行或超出资源

研究设计 Agent ↔ 科研计算与数据分析 Agent
条件：分析不可行或数据结构不匹配

独立审稿 Agent → 研究设计 Agent
条件：方法、变量、样本、测量或因果推断存在缺陷
```

---

## 7. 科研计算与数据分析 Agent

### 7.1 定位

科研计算与数据分析 Agent 负责数据问题诊断、数据处理建议、分析计划细化、代码规格生成、统计方法建议和结果解释边界。

它不能直接修改真实数据，也不能修改正式统计结果。

### 7.2 双阶段运行方式

该 Agent 在科研流程中至少运行两次：

```text
数据采集前
→ 检查分析可行性并生成分析规格

数据采集后
→ 诊断数据、验证结果并形成解释边界
```

### 7.3 数据采集前输入

```text
ApprovedStudyProtocol
ApprovedPreregisteredAnalysisPlan
DataCollectionSchema
MeasurementPlan
VariableDictionary
AnalysisMode
```

### 7.4 数据采集前输出

```text
DataValidationRuleCandidate
DataAuditSpecification
DataProcessingPlanCandidate
ExecutableAnalysisPlanCandidate
CodeSpecificationDraft
SchemaCompatibilityRequirement
ResultValidationPlan
```

### 7.5 数据采集后输入

```text
RawDatasetRef
DataDictionaryRef
DataAuditReportRef
ApprovedDataProcessingPlanRef
ProcessedDatasetRef
FrozenDatasetRef
ExecutionRunRef
RawResultArtifactRef
StatisticalResultCardRef
```

### 7.6 数据采集后处理过程

#### 数据诊断

```text
缺失值
异常值
重复记录
组别不平衡
变量编码错误
Schema 不匹配
```

#### 分析方案确认

```text
回归分析
ANCOVA
ANOVA
线性混合效应模型
IRT
SEM
中介或调节分析
```

#### 代码规格生成

```text
输入数据版本
变量名称
主要模型
协变量
随机种子
效应量
置信区间
输出表格
输出图形
验证规则
```

#### 结果解释边界

区分：

```text
预注册分析
探索性分析
描述性发现
统计结果
因果解释
研究限制
```

### 7.7 输出

```text
DataIssueReport
AnalysisReadinessReport
DataProcessingPlanCandidate
CodeSpecificationDraft
ModelDiagnosticRecommendation
ResultInterpretationBoundary
StatisticalResultCardCandidate
RiskFlags
```

### 7.8 ToolRequest

```text
DataAuditOperator
DataProcessingOperator
DataFreezeOperator
CodingProviderOperator
PythonAnalysisOperator
SPSSOperator
ResultValidationOperator
```

所有工具请求都必须经过 Controller。

### 7.9 重新调用条件

```text
数据结构不匹配
模型不可执行
结果异常
结果无法复现
统计数字不一致
分析偏离预注册
现有数据无法回答研究问题
```

### 7.10 与其他 Agent 的动态关系

```text
科研计算与数据分析 Agent ↔ 研究设计 Agent
条件：数据结构或统计方案不匹配

科研计算与数据分析 Agent ↔ 证据综述 Agent
条件：异常结果需要外部理论或实证解释

科研计算与数据分析 Agent ↔ 论文写作 Agent
条件：结果信息不足、统计数字不一致、图表缺失

独立审稿 Agent → 科研计算与数据分析 Agent
条件：分析错误、代码或数据版本不一致、结果不可复现
```

---

## 8. 论文写作 Agent

### 8.1 定位

论文写作 Agent 负责把已核验证据、已批准协议和已验证结果组织为可追溯论文。

它不能凭空创造结果，也不能修改统计数字。

### 8.2 输入

```text
VerifiedEvidenceMatrix
ApprovedResearchQuestion
ApprovedStudyProtocol
PreregisteredAnalysisPlan
StatisticalResultCard
ResultValidationReport
ResultInterpretationBoundary
ApprovedTablesAndFigures
TargetJournalRequirements
ContextBundle
```

### 8.3 处理过程

#### 论文结构生成

```text
Title
Abstract
Introduction
LiteratureReview
Method
Results
Discussion
Limitations
Conclusion
ReproducibilityStatement
```

#### AtomicClaim 拆分

每条核心主张只能属于一个类型：

```text
LITERATURE
RESULT
METHOD
INTERPRETATION
SPECULATION
LIMITATION
```

示例：

```text
RESULT：
分层渐退组的无 AI 迁移成绩高于自由 AI 组。

INTERPRETATION：
渐退式支架可能有助于学生保持独立建模能力。

LIMITATION：
样本来自单一师范院校，外部效度有限。
```

#### Claim 追溯

```text
Claim
→ EvidenceRef 或 StatisticalResultCardRef
→ SourceChunk 或 ExecutionRun
→ 原始来源、数据、代码与版本
```

### 8.4 输出

```text
AtomicClaimCandidate
ClaimEvidenceMap
ManuscriptOutline
ManuscriptDraft
AbstractDraft
TableFigureNarrative
LimitationsDraft
ReproducibilityStatement
```

### 8.5 重新调用条件

```text
引用不足
Claim 缺少证据
结果数字不一致
方法描述与协议不一致
结论超过实验边界
探索性分析被写成验证性分析
论文结构或表达不合格
```

### 8.6 与其他 Agent 的动态关系

```text
论文写作 Agent ↔ 证据综述 Agent
条件：引用缺失或讨论需要补充证据

论文写作 Agent ↔ 科研计算与数据分析 Agent
条件：结果信息不足、统计数字不一致

独立审稿 Agent → 论文写作 Agent
条件：表达、结构或 AtomicClaim 不合格
```

---

## 9. 独立审稿 Agent

### 9.1 定位

独立审稿 Agent 模拟独立科研审查。

它不负责修改工件，只负责发现问题、给出严重等级和生成修订请求。

### 9.2 内部 Reviewer

```text
Citation Reviewer
Method Reviewer
Reproducibility Reviewer
Pedagogy Reviewer
Review Arbiter
```

### 9.3 输入

```text
ManuscriptDraft
AtomicClaimCandidate
ClaimEvidenceMap
EvidenceMatrix
StudyProtocol
PreregisteredAnalysisPlan
CodeArtifactRef
ExecutionRunRef
StatisticalResultCard
ProvenanceRef
ContextBundle
```

### 9.4 审查内容

#### Citation Reviewer

```text
引用是否真实
主张是否被引用支持
引用是否能反查原文
是否使用未核验证据
是否存在断章取义
```

#### Method Reviewer

```text
研究问题和设计是否一致
Estimand 是否明确
变量、样本和测量是否合理
统计方法是否符合预注册计划
因果语言是否越界
```

#### Reproducibility Reviewer

```text
数据是否冻结
代码版本是否记录
运行环境是否记录
随机种子是否记录
结果能否反查 ExecutionRun
论文数字是否与结果卡一致
```

#### Pedagogy Reviewer

```text
AI 支架设计是否符合教学逻辑
迁移任务是否真正测量迁移
提示依赖指标是否合理
对职前教师的解释是否成立
```

#### Review Arbiter

```text
PASS
MINOR_REVISION
MAJOR_REVISION
BLOCK
```

### 9.5 输出

```text
ReviewFinding
RevisionRequest
ReviewReport
OverallRecommendation
```

### 9.6 问题回流规则

| 审稿问题 | 返回模块 |
|---|---|
| 研究贡献不足、范围不合理 | 导师规划 Agent |
| 引用错误、证据不足、遗漏文献 | 证据综述 Agent |
| 设计、变量、样本、测量或因果逻辑缺陷 | 研究设计 Agent |
| 统计、代码、数据或复现问题 | 科研计算与数据分析 Agent |
| 结构、语言、Claim 或解释越界 | 论文写作 Agent |

### 9.7 审稿通过后

```text
独立审稿 Agent
→ ReviewReport: PASS
→ Controller
→ Human Approval
→ RELEASED
```

Reviewer 不能直接发布。

---

## 10. 六 Agent 的动态协作关系

STEM-SCI 的核心不是六个 Agent 线性调用，而是围绕 Controller 进行动态路由。

```text
                     研究者需求与项目画像
                              ↓
                        导师规划 Agent
                              ↓
               科研流程监督调度与 Gate Controller
                 ↙           ↓           ↘
        证据综述 Agent  ←→ 研究设计 Agent ←→ Operator
             ↕                  ↕
        知识库              科研计算与数据分析 Agent
             ↖                  ↕
                 论文写作 Agent
                        ↓
                   独立审稿 Agent
                  ↙   ↓   ↘
             定向返工 / 审稿通过
                        ↓
        更新科研项目画像、ResearchState 与长期记忆
                        ↓
                    下一轮调度
```

主要交叉关系：

```text
导师规划 Agent ↔ 证据综述 Agent
导师规划 Agent ↔ 研究设计 Agent
证据综述 Agent ↔ 研究设计 Agent
证据综述 Agent ↔ 科研计算与数据分析 Agent
证据综述 Agent ↔ 论文写作 Agent
研究设计 Agent ↔ 科研计算与数据分析 Agent
科研计算与数据分析 Agent ↔ 论文写作 Agent
独立审稿 Agent → 前五个 Agent
```

这些交互在语义上都应经过 Controller：

```text
Agent A 输出
→ Controller 判断
→ Agent B 输入
```

Agent 不直接越权调度另一个 Agent。

---

## 11. 典型运行案例

### 11.1 用户输入

```text
研究分层渐退式生成式 AI 支架
是否能够提高职前教师的 Python 物理建模能力、
无 AI 迁移能力并降低提示依赖
```

### 11.2 导师规划 Agent

输出：

```text
研究范围
研究问题树
可行性报告
文献需求
项目路线
```

### 11.3 证据综述 Agent

输出：

```text
生成式 AI 编程教育证据
教学支架证据
无 AI 迁移证据
提示依赖证据
EvidenceMatrix
ResearchGapReport
```

### 11.4 研究设计 Agent

输出：

```text
实验组：
分层渐退 AI

对照组一：
自由使用 AI

对照组二：
传统学习

训练任务：
抛体运动、弹簧振子

迁移任务：
无 AI 单摆或冷却定律建模
```

### 11.5 科研计算与数据分析 Agent

输出：

```text
主要结果：
无 AI 迁移成绩

主要模型：
ANCOVA 或线性回归

重复测量：
线性混合效应模型

结果输出：
效应量、置信区间、StatisticalResultCard
```

### 11.6 论文写作 Agent

输出：

```text
AtomicClaimCandidate
ClaimEvidenceMap
ManuscriptDraft
```

### 11.7 独立审稿 Agent

发现：

```text
迁移任务与训练任务过于相似，
不能充分证明远迁移。
```

生成：

```text
RevisionRequest
→ research_design_agent
```

Controller 重新调用研究设计 Agent，修改迁移任务，之后再次进入分析与审稿。

---

## 12. 系统最终目标

STEM-SCI 不是简单的：

```text
LLM + 多个工具
```

而是：

```text
ResearchState
+
Controller
+
Multi-Agent Reasoning
+
Evidence Traceability
+
Executable Research Protocol
+
Operator Execution
+
Independent Review
+
Human Approval
```

最终形成：

```text
自然语言研究构想
→ 可执行科研协议
→ 真实教学实验
→ 可验证科研数据
→ 可复现统计结果
→ 可追溯论文主张
→ 经独立审查和人工批准的科研成果
```
