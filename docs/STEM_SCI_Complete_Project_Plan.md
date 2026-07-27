# STEM-SCI 项目完整规划书

> **项目名称：** STEM-SCI：面向教育学一流学科建设的可追溯科研智能体系统  
> **项目副标题：** 聚焦 STEM 编程教育实验的研究协议编译、教学实验评价、科研数据分析与证据追溯  
> **文档版本：** v1.0  
> **当前阶段：** Phase 0 已完成，Phase 1 准备启动  
> **文档用途：** 团队统一理解、任务拆分、开发实施、比赛申报和后续验收  
> **优先级说明：** 本文档整合当前已确认的最终决策。团队开发、设计和答辩材料应以本文档为统一依据。

---

# 目录

1. 项目摘要  
2. 赛题与学科定位  
3. 项目解决的问题  
4. 产品边界  
5. 核心设计原则  
6. 五个核心创新  
7. 用户与应用场景  
8. 主 Demo 研究案例  
9. 系统总体架构  
10. 六类专业 Agent  
11. Operator Registry  
12. 高级流程控制  
13. 完整科研业务流程  
14. Research Protocol Compiler  
15. 文献证据与 GraphRAG  
16. 研究设计与预注册  
17. STEM 编程教育实验引擎  
18. 学生代码评价  
19. Feedback Firewall  
20. 数据三层版本管理  
21. 科研分析代码与统计执行  
22. 结果验证与 StatisticalResultCard  
23. Atomic Claim 与论文写作  
24. 独立审稿机制  
25. 全链路科研溯源  
26. 教育研究复现审计模式  
27. 核心数据结构  
28. ResearchState 与存储分层  
29. 安全、隐私、伦理与科研诚信  
30. 项目目录结构  
31. Phase 0—Phase 8 实施路线  
32. Phase 1 当前开发范围  
33. 自动化测试与不变量  
34. 比赛 Demo 设计  
35. 效果验证与评估方案  
36. 与评分标准的对应关系  
37. 团队分工建议  
38. 里程碑与协作方式  
39. 风险、过度设计与降级策略  
40. 当前未决事项  
41. 接下来两周的执行清单  
42. 术语表  
43. 最终统一表述

---

# 1. 项目摘要

STEM-SCI 是一个面向教育学一流学科建设、聚焦 STEM 编程教育实验研究的可追溯科研智能体系统。

系统服务的主要用户包括：

- 高校教育学教师；
- 教育技术学研究人员；
- STEM 教育研究团队；
- 教育学硕士和博士研究生；
- 师范生培养和教师教育团队；
- 高校实验室及科研管理团队。

STEM-SCI 不是简单的聊天机器人，也不是自动论文生成器。系统将研究者的自然语言构想编译成一组结构化、可执行、可审批、可验证和可复现的科研协议，并协调文献检索、研究设计、STEM 编程任务、学生代码评价、数据管理、统计分析、论文写作和独立审稿等环节。

系统建立以下完整链路：

```text
研究构想
→ 文献证据
→ 研究问题
→ 研究设计
→ 教学干预
→ STEM 编程任务
→ 学生代码与学习过程
→ Raw / Processed / Frozen 数据
→ 分析计划
→ 科研分析代码
→ SPSS / Python 真实执行
→ 统计结果卡片
→ 论文原子主张
→ 独立审稿
→ 复现包与发布
```

整个系统的核心不是“生成更多文字”，而是：

> **让教育科研过程更加规范、可信、可执行、可验证、可追溯和可复现。**

---

# 2. 赛题与学科定位

## 2.1 一级学科定位

```text
一级学科：教育学
```

## 2.2 垂直研究方向

```text
教育技术学
科学教育
课程与教学论
STEM 教育
编程教育
教师教育
```

## 2.3 首个聚焦场景

```text
STEM 编程教育实验研究
```

STEM 编程教育不是一级学科，而是教育学中的具体研究方向和科研场景。

## 2.4 与“一流学科建设”的关系

系统通过以下方式服务教育学一流学科建设：

1. 提高教育研究设计的规范性；
2. 提高科研数据分析的准确性和可复现性；
3. 形成高质量教育学文献、量表、研究协议和案例资产；
4. 服务教育学硕博研究生科研训练；
5. 支撑教育学实验室的科研协作和知识沉淀；
6. 降低虚假文献、错误统计和过度解释风险；
7. 支持高校教师和学生开展真实教育科研项目；
8. 促进教育学与人工智能、编程教育和数据科学交叉融合。

---

# 3. 项目解决的问题

当前教育科研通常需要分别使用文献检索工具、统计软件、代码工具、论文写作工具和项目管理工具。不同环节彼此割裂，存在以下问题。

## 3.1 研究构想难以转化为可执行方案

研究者可能只输入：

> 我想研究 AI 提示对编程学习有没有帮助。

但该表述缺少：

- 研究对象；
- 干预和对照；
- 结果变量；
- 理论依据；
- 可执行任务；
- 样本规模；
- 伦理条件；
- 分析计划。

## 3.2 文献证据与研究问题脱节

常见问题：

- 只做关键词搜索，不形成检索协议；
- 文献结论无法定位原文；
- 将“没有检索到”写成“从未有人研究”；
- 忽略反向证据和冲突结论；
- 不同论文证据权重被视为相同。

## 3.3 教学实验与统计分析脱节

STEM 编程教育研究中，教学任务、AI 提示、Rubric、变量和分析方法经常不一致。

例如：

- 研究目标是“建模能力”，但只测代码能否运行；
- 研究目标是“学习效果”，但只测 AI 帮助下的即时表现；
- AI 提示直接给出完整代码，导致实验失去意义；
- 任务 A 和任务 B 难度不同，却直接比较分数。

## 3.4 数据版本和分析过程难以复现

常见问题：

- 原始数据被覆盖；
- 数据清洗步骤无记录；
- 正式分析读取了错误数据版本；
- 统计代码、软件设置和论文数字不一致；
- SPSS 和 Python 使用不同案例集合；
- 结果没有代码哈希、数据哈希和运行环境。

## 3.5 AI 科研风险

大模型可能：

- 虚构文献；
- 虚构统计结果；
- 生成不存在的 API；
- 隐藏不显著结果；
- 过度使用因果语言；
- 将探索性结果写成确认性结果；
- 根据结果反向选择分析方法；
- 将学生完成任务误判为真正学习。

---

# 4. 产品边界

STEM-SCI 明确不属于以下系统：

- 普通教育学问答机器人；
- 自动代写论文工具；
- 六个 Agent 自由聊天平台；
- 固定排队式多 Agent 系统；
- 大模型直接“心算”统计结果的工具；
- 仅做文献摘要的工具；
- 仅做学生代码批改的平台；
- 完全自主科研系统；
- 无人监督的“自动科学家”；
- 自动投稿系统。

系统不允许：

- Agent 自行决定正式研究问题；
- Agent 自行修改 `current_stage`；
- Agent 自行冻结正式数据；
- Agent 修改真实统计数字；
- Codex 根据结果决定分析方法；
- 写作 Agent 创造文献或数字；
- Reviewer 直接覆盖正式工件；
- 未经人工批准发布研究结论。

---

# 5. 核心设计原则

## 5.1 Controller 独占流程控制权

只有 Controller 可以：

- 修改 `current_stage`；
- 根据 Gate 和风险做流程路由；
- 发起 Operator；
- 合并 AgentResult；
- 创建审批请求；
- 进入 REWORK、BLOCKED、WAITING_HUMAN 或 FAILED；
- 推进正式研究阶段。

## 5.2 Agent 只负责专业推理

Agent 只返回结构化 `AgentResult`，包括：

- 候选工件；
- 问题；
- 建议；
- 风险提示；
- 需要的工具；
- 需要的人类决定。

Agent 不能直接改变系统状态。

## 5.3 Operator 执行确定性操作

Operator 负责：

- 检索；
- 文件处理；
- 数据审计；
- 数据冻结；
- 代码执行；
- SPSS / Python 分析；
- 哈希校验；
- 沙箱运行；
- 溯源写入；
- 科研单元测试。

## 5.4 人类保留科研决定权

以下事项必须由人类批准：

- 最终研究问题；
- 文献纳排标准；
- 研究设计；
- 伦理边界；
- 主要结果变量；
- 预注册分析计划；
- 数据处理方案；
- 分析计划修订；
- 关键结果解释；
- 最终发布。

## 5.5 所有正式结论必须真实执行

正式结果必须关联：

```text
FrozenDataset
CodeArtifact
ExecutionRun
ResultValidationReport
StatisticalResultCard
```

任何没有真实执行记录的数字不得进入正式论文。

## 5.6 大对象引用化

`ResearchState` 中只保存引用，不保存：

- PDF 全文；
- 完整数据；
- 学生代码正文；
- 科研代码正文；
- 图片；
- SPSS 输出；
- 完整日志；
- 大型 Agent 对话。

## 5.7 版本、审批和溯源优先

正式科研工件必须具备：

```text
version
schema_version
created_at
created_by
supersedes_ref
```

正式人工决策统一保存为 `ApprovalRecord`，科研工件只引用 `approval_ref`。

---

# 6. 五个核心创新

## 6.1 Research Protocol Compiler

### 作用

将自然语言研究想法编译为结构化科研协议。

### 输入

- 研究主题；
- 目标用户；
- 研究对象；
- 时间和资源约束；
- 文献证据；
- 伦理边界；
- 已有数据。

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

### 与普通大模型的区别

普通大模型生成文字建议；Research Protocol Compiler 生成具有 Schema、版本、审批状态和质量 Gate 的可执行科研工件。

---

## 6.2 Rubric-driven Research Unit Testing

### 作用

为每个科研工件运行可执行检查。

### 示例

研究问题测试：

```text
研究对象是否明确
干预是否可操作
对照是否明确
主要结果是否唯一
是否能被当前设计回答
是否存在不可识别因果问题
```

研究方案测试：

```text
样本是否有功效分析
是否识别班级和教师混淆
干预是否可复现
伦理字段是否完整
StudyProtocol 与 Estimand 是否一致
```

统计结果测试：

```text
数据哈希是否一致
代码哈希是否一致
案例集合是否一致
效应量和置信区间是否存在
结果解释是否超过设计边界
```

---

## 6.3 Agent–Evidence–Execution–Claim Provenance Graph

### 作用

记录研究决策和研究结论的完整来源。

### 追溯链

```text
用户输入
→ RouteDecision
→ AgentRunRecord
→ OperatorRun
→ 工件版本
→ 文献证据
→ 数据版本
→ 代码
→ 执行
→ 结果
→ AtomicClaim
→ 论文句子
```

### 可回答的问题

- 该结论由谁生成？
- 使用了哪个研究方案？
- 使用了哪个数据版本？
- 使用了哪段代码？
- 在什么环境运行？
- 是否经过人工审批？
- 是否经过 SPSS / Python 复核？
- 该结论出现在论文哪一句？

---

## 6.4 Risk-aware Research Orchestration Engine

### 作用

根据风险、质量、预算和人工影响动态决定下一步。

### 风险维度

```text
MethodRisk
CitationRisk
PedagogyRisk
PrivacyRisk
ReproducibilityRisk
CausalOverclaimRisk
AnswerLeakageRisk
Uncertainty
HumanImpact
BudgetUsage
```

### 路由优先级

```text
安全与科研诚信硬规则
→ 人工审批规则
→ Research Unit Test 与 Gate
→ 风险评分
→ 预算策略
→ 模型建议
```

模型建议不得覆盖硬规则。

---

## 6.5 教学有效性与科研有效性双闭环

### 教学闭环

```text
学生代码
→ LearnerCodeSandbox
→ 自动测试
→ Rubric 评分
→ 错误诊断
→ 分层提示
→ Feedback Firewall
→ 学生修改
→ 无 AI 迁移任务
→ 独立能力和提示依赖评价
```

### 科研闭环

```text
PreregisteredAnalysisPlan
→ FrozenDataset
→ ExecutableAnalysisPlan
→ CodeSpecification
→ Codex / CodingProvider
→ SPSS / Python 执行
→ ResultValidationReport
→ StatisticalResultCard
→ AtomicClaim
→ 独立审稿
```

---

# 7. 用户与应用场景

## 7.1 主要用户

### 教育学教师

需求：

- 设计教育实验；
- 管理文献证据；
- 分析教学数据；
- 检查论文结论；
- 形成可复现科研包。

### 教育学硕博研究生

需求：

- 明确研究问题；
- 规范研究设计；
- 选择统计方法；
- 减少错误引用和错误分析；
- 学习规范科研流程。

### STEM 教师教育团队

需求：

- 设计编程教学任务；
- 分析学生代码；
- 评价 AI 教学支架；
- 研究无 AI 迁移能力；
- 形成教师行动研究报告。

### 实验室或科研管理团队

需求：

- 项目版本管理；
- 研究审批；
- 复现审计；
- 研究质量监控；
- 团队知识资产沉淀。

## 7.2 两种主要产品模式

### 模式 A：新研究构建模式

```text
研究想法
→ 研究协议
→ 教学实验
→ 数据
→ 分析
→ 论文
```

### 模式 B：已有研究复现审计模式

```text
论文 + 数据 + 代码 + 补充材料
→ 重新执行
→ 数字核验
→ 方法审计
→ 结论审计
→ ReproductionAuditReport
```

---

# 8. 主 Demo 研究案例

## 8.1 最终题目

> **生成式 AI 分层支架对师范生 Python 物理建模表现、无辅助迁移能力和提示依赖的影响：一项随机平行组重复测量实验。**

## 8.2 研究对象

```text
师范生或教育技术学本科生
```

使用师范生作为主 Demo 对象，更直接对应：

- 高等教育；
- 教育学；
- 教师培养；
- 一流学科建设；
- STEM 教育；
- 编程教学。

## 8.3 实验条件

```text
实验组：
任务 A、任务 B 使用生成式 AI 分层支架

对照组：
任务 A、任务 B 使用静态提示

两组：
最终完成无 AI 任务 C

任务 A/B 顺序：
随机平衡

干预条件：
不交叉
```

## 8.4 三个编程任务

### 任务 A：Python 抛体运动建模

学生需要实现：

- 输入初速度、角度、步长和重力加速度；
- 角度转弧度；
- 分解水平和竖直速度；
- 逐步更新位置；
- 判断落地；
- 输出飞行时间、最高点、射程；
- 绘制轨迹；
- 与理论结果比较。

### 任务 B：Python 弹簧振子建模

学生需要实现：

- 定义质量、弹簧系数和初始位移；
- 建立运动方程；
- 使用数值方法计算位移；
- 绘制时间—位移曲线；
- 分析周期和参数变化；
- 与理论周期比较。

### 任务 C：无 AI 迁移任务

任务应使用不同情境，例如：

- 阻尼振动；
- 斜面运动；
- 简化人口增长模型；
- 热传导离散模拟。

目的：

- 测量学生独立建模能力；
- 避免把 AI 帮助下的完成表现等同于学习效果；
- 计算提示依赖和独立迁移指标。

## 8.5 主要结果维度

```text
代码正确性
物理模型正确性
数值计算准确性
代码结构与可读性
调试效率
提示使用情况
提示依赖程度
解释能力
无 AI 迁移表现
认知负荷
学习投入
```

## 8.6 研究设计注意事项

本实验是平行组重复测量，不是经典交叉实验。

需要处理：

```text
condition effect
task effect
period / time effect
task sequence effect
participant repeated measures
prior ability
condition × task interaction
```

任务 A/B 需要形成 `TaskEquivalenceReport`。

---

# 9. 系统总体架构

```text
┌──────────────────────────────────────────────┐
│               用户科研工作台                  │
│ 项目 / 文献 / 协议 / 实验 / 数据 / 写作 / 审批 │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│          Research Protocol Compiler          │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│      Risk-aware Research Controller          │
│ 状态机 / 路由 / 风险 / 预算 / 审批 / 恢复      │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│       Research Unit Test & Gate Engine       │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│                六类专业 Agent                 │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│                专业 Subgraph                  │
│ Literature / Design / Experiment / Analysis  │
│ Writing / Reproduction Audit                 │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│              Operator Registry               │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ GraphRAG / Memory / Store / Sandbox / Tools   │
└─────────────────────┬────────────────────────┘
                      ↓
┌──────────────────────────────────────────────┐
│ Agent–Evidence–Execution–Claim Provenance    │
└──────────────────────────────────────────────┘
```

---

# 10. 六类专业 Agent

## 10.1 导师规划 Agent

### 负责

- 澄清研究构想；
- 定义研究范围；
- 生成研究问题树；
- 判断初步可行性；
- 形成理论框架候选；
- 生成项目路线。

### 输出

```text
ResearchContract
FeasibilityReport
ResearchQuestionTree
TheoryFramework
ProjectRoadmap
```

### 禁止

- 自动确定最终研究问题；
- 自动批准研究范围；
- 编造研究结论。

---

## 10.2 证据综述 Agent

### 负责

- 构建检索协议；
- 文献筛选；
- PaperCard 抽取；
- 证据矩阵；
- 冲突证据；
- 研究空白；
- 查新。

### 输出

```text
SearchProtocol
PRISMALedger
PaperCard
EvidenceMatrix
ContradictionMap
NoveltyReport
ResearchGapReport
```

### 文献关系

```text
SUPPORTING
CONTRASTING
MENTIONING
```

### 禁止

- 使用模型记忆代替真实来源；
- 将未检索到直接写成从未研究；
- 将未核验内容写进正式结论。

---

## 10.3 研究设计 Agent

### 负责

- 生成候选研究设计；
- 提出 Estimand；
- 构建 CausalDAG；
- 设计样本和分组；
- 设计变量和测量；
- 设计教学干预；
- 提出 AnalysisPlan 草案；
- 设计功效分析和预注册。

### 输出

```text
CandidateStudyDesign
Estimand
CausalDAG
StudyProtocol
VariableDictionary
SamplingPlan
InstrumentPlan
PowerAnalysis
PreregisteredAnalysisPlanDraft
EthicsChecklist
```

### 禁止

- 根据结果改变分析方法；
- 自动批准研究设计；
- 自动删除异常值；
- 自动决定伦理边界。

---

## 10.4 科研计算与数据分析 Agent

### 负责

- 数据问题诊断；
- 数据处理建议；
- CodeSpecification 草案；
- 方法边界；
- 结果解释边界；
- 稳健性检查建议。

### 输出

```text
DataAuditReport
DataProcessingSuggestions
CodeSpecificationDraft
ExecutionDiagnosis
ResultInterpretationBoundary
RobustnessCheckPlan
```

### 禁止

- 修改 RawDataset；
- 自行冻结数据；
- 修改预注册分析计划；
- 选择性隐藏结果；
- 修改执行数字。

---

## 10.5 论文写作 Agent

### 负责

- Atomic Claim 生成；
- ClaimEvidenceMap；
- IMRaD 草稿；
- 摘要；
- 汇报稿；
- PPT 文案。

### 只允许使用

- 已核验文献；
- 已批准方法；
- 已验证结果；
- 已确认解释边界。

### 禁止

- 创造文献；
- 创造数字；
- 增加未执行分析；
- 将推测写成结果；
- 将准实验结果写成无限制因果结论。

---

## 10.6 独立审稿 Agent

内部包含：

```text
Citation Reviewer
Method Reviewer
Reproducibility Reviewer
Pedagogy Reviewer
Review Arbiter
```

Reviewer 只输出：

```text
ReviewFinding
RevisionRequest
ReviewReport
```

Reviewer 不得：

- 直接修改正式工件；
- 修改 current_stage；
- 修改 StatisticalResultCard；
- 覆盖人工审批；
- 直接发布结果。

---

# 11. Operator Registry

## 11.1 设计目的

Operator 层解决以下问题：

- Controller 不与具体工具耦合；
- Codex 可替换；
- SPSS 可降级；
- Python 执行可独立；
- 不同检索工具可替换；
- 所有工具统一记录输入、输出、权限、成本和错误。

## 11.2 Operator 列表

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

## 11.3 OperatorSpec

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

## 11.4 OperatorRun

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

# 12. 高级流程控制

## 12.1 顶层状态机

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

## 12.2 状态分层

不能只维护一个项目状态。

```text
ProjectStage
TaskStatus
ArtifactStatus
RunStatus
```

## 12.3 DecisionScope

```text
RUN
ARTIFACT
TASK
STAGE
PROJECT
```

示例：

```text
学生代码访问网络
→ BLOCKED RUN

单篇 DOI 无效
→ REJECTED ARTIFACT

统计任务失败
→ REWORK TASK

FrozenDataset 哈希异常
→ BLOCKED STAGE

缺少合法数据或伦理许可
→ BLOCKED PROJECT
```

## 12.4 Gate 决策

```text
PASS
PASS_WITH_WARNING
REWORK
BLOCKED
WAITING_HUMAN
FAILED
```

## 12.5 自动返工与停滞

```text
第一次失败：
原 Agent 或 Operator 定向修复

第二次失败：
Controller 拆解任务或更换 Operator

第三次失败：
WAITING_HUMAN

缺少真实证据、真实数据、伦理条件或合法权限：
直接 BLOCKED
```

## 12.6 BudgetState

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

第一版采用规则预算，不做复杂自动优化。

---

# 13. 完整科研业务流程

## 阶段 0：项目创建

用户填写：

```text
研究主题
研究对象
教学场景
预期成果
可用时间
可用数据
伦理条件
```

输出：

```text
ProjectMeta
project_id
run_id
```

---

## 阶段 1：可行性评估

系统检查：

- 研究对象；
- 干预；
- 对照；
- 结果变量；
- 数据来源；
- 样本可得性；
- 伦理；
- 隐私；
- 可识别性；
- 时间和资源。

输出：

```text
ResearchContract
FeasibilityReport
```

---

## 阶段 2：文献检索协议

输出：

```text
SearchProtocol
数据库范围
检索式
时间范围
语言范围
纳入标准
排除标准
抽取字段
```

由人工批准。

---

## 阶段 3：文献证据综合

```text
检索
→ 去重
→ 标题摘要筛选
→ 全文筛选
→ PaperCard
→ EvidenceMatrix
→ ContradictionMap
→ NoveltyReport
→ ResearchGapReport
```

---

## 阶段 4：研究问题与候选设计

系统可生成多个候选设计：

```text
随机平行组重复测量
准实验
交叉设计候选
混合研究
单组前后测
```

评分维度：

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

研究者最终选择。

---

## 阶段 5：研究设计与预注册

形成：

```text
ResearchQuestion
Hypothesis
Estimand
CausalDAG
StudyProtocol
PowerAnalysis
PreregisteredAnalysisPlan
PreregistrationSnapshot
```

必须在数据采集和结果查看前批准。

---

## 阶段 6：STEM 编程任务设计

形成：

```text
ProgrammingTaskSpecification
InterventionProtocol
HintPolicy
CodeRubric
UnitTestSpecification
TaskEquivalenceReport
TeachingFidelityChecklist
```

---

## 阶段 7：实验执行

记录：

```text
参与者匿名 ID
分组
任务顺序
代码版本
测试结果
提示请求
提示级别
提示内容
代码变化
任务完成
```

---

## 阶段 8：数据管理

```text
RawDataset
→ DataAuditReport
→ DataProcessingPlan
→ ProcessedDataset
→ FrozenDataset
```

---

## 阶段 9：可执行分析计划

```text
PreregisteredAnalysisPlan
+ FrozenDataset Schema
→ ExecutableAnalysisPlan
→ SchemaCompatibilityGate
```

ExecutableAnalysisPlan 只能处理：

- 变量映射；
- 类型确认；
- case filter 映射；
- 软件配置；
- 执行模式。

不能改变实质性分析决定。

---

## 阶段 10：代码生成和执行

```text
ExecutableAnalysisPlan
→ CodeSpecification
→ Codex / CodingProvider
→ CodeArtifact
→ CodeReviewGate
→ Python / SPSS 执行
```

---

## 阶段 11：结果验证

```text
ExecutionRun
→ ResultValidationReport
→ StatisticalResultCard
```

---

## 阶段 12：写作和审稿

```text
StatisticalResultCard
→ AtomicClaim
→ ClaimEvidenceMap
→ ManuscriptDraft
→ 多维 Reviewer
→ Human Approval
→ RELEASED
```

---

# 14. Research Protocol Compiler

## 14.1 编译过程

```text
自然语言研究想法
→ 意图和实体解析
→ 缺失字段识别
→ 可行性检查
→ 文献检索需求
→ 结构化研究问题
→ 候选设计
→ 正式研究协议对象
```

## 14.2 研究协议对象

```text
ResearchContract
ResearchQuestion
Hypothesis
Estimand
CausalDAG
StudyProtocol
InterventionProtocol
ProgrammingTaskSpecification
DataCollectionSchema
PreregisteredAnalysisPlan
EthicsChecklist
QualityGatePlan
```

## 14.3 Bounded Research Design Search

只在数据采集前使用。

流程：

```text
生成 3 个候选设计
→ Method Reviewer 评价
→ Controller 保留前 2 个
→ 研究者选择
```

禁止：

- 根据显著性选择方法；
- 自动修改预注册计划；
- 自动改变正式数据；
- 自动发布研究结论。

---

# 15. 文献证据与 GraphRAG

## 15.1 GraphRAG 作用

GraphRAG 用于：

- 文献检索；
- 理论检索；
- 量表检索；
- 研究方法检索；
- 原文证据定位；
- 项目知识检索。

GraphRAG 不替代来源核验。

## 15.2 PaperCard

建议字段：

```text
paper_id
title
authors
year
doi
source_uri
source_hash
research_context
sample
study_design
intervention
comparison
outcomes
methods
results
limitations
risk_of_bias
causal_strength
source_locations
verification_status
```

## 15.3 EvidenceMatrix

记录：

```text
claim
supporting evidence
contrasting evidence
source location
quality
verification status
conflict status
```

## 15.4 来源状态

```text
demo_seed
model_generated_unverified
source_verified
human_verified
```

规则：

- Agent 不能写 `human_verified`；
- 未核验内容不能支持正式主张；
- 文献正式结论必须至少 `source_verified`。

## 15.5 向量库策略

MVP：

```text
统一多语言嵌入模型
统一向量维度
一个 Collection
```

后续如使用两个嵌入模型：

```text
两个独立 Collection
→ 分数归一化
→ RRF
→ MMR
```

禁止不同维度向量进入同一 Collection。

---

# 16. 研究设计与预注册

## 16.1 Estimand

Estimand 明确研究真正要估计的对象。

示例：

```text
Population：
参加 Python 物理建模课程的师范生

Treatment：
生成式 AI 分层支架

Comparator：
静态提示

Outcome：
无 AI 迁移任务成绩

Time：
实验结束后

Estimand：
平均处理效应
```

## 16.2 CausalDAG

用于判断：

- 混淆变量；
- 中介变量；
- 共同原因；
- 不能控制的变量；
- 因果表述边界。

## 16.3 PreregisteredAnalysisPlan

必须在数据采集或结果查看前冻结。

包含：

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
```

## 16.4 ExecutableAnalysisPlan

在 FrozenDataset 后生成。

只能包含：

```text
variable_mapping
variable_type_confirmations
case_filter_mapping
software_configuration
execution_mode
schema_compatibility_status
```

## 16.5 AnalysisPlanAmendment

任何实质性修改必须记录：

```text
affected_fields
change_summary
reason
created_at
results_viewed_at_amendment
classification
human_approval_ref
```

分类：

```text
CONFIRMATORY
EXPLORATORY
```

---

# 17. STEM 编程教育实验引擎

## 17.1 核心工件

```text
ProgrammingTaskSpecification
InterventionProtocol
HintPolicy
CodeRubric
UnitTestSpecification
TaskEquivalenceReport
TeachingFidelityChecklist
InterventionFidelityReport
```

## 17.2 TaskEquivalenceReport

比较任务 A/B：

```text
物理知识点数量
数学难度
代码长度
预计完成时间
错误机会数量
自动测试覆盖率
教师专家评分
预实验结果
```

## 17.3 InterventionFidelityReport

检查：

- 实验组是否实际使用 AI；
- 对照组是否接触 AI；
- 教师是否按方案执行；
- 教学时间是否一致；
- 提示等级是否符合策略；
- AI 是否泄露答案；
- 是否出现干预污染。

---

# 18. 学生代码评价

## 18.1 两类代码严格分离

```text
LearnerCodeArtifact
ResearchCodeArtifact
```

## 18.2 两个沙箱

```text
LearnerCodeSandbox
ResearchCodeSandbox
```

### LearnerCodeSandbox

用于运行学生代码。

限制：

- 禁止网络；
- 禁止宿主文件；
- 禁止系统命令；
- 限制 CPU、内存和时间；
- 只读取指定测试数据；
- 只写当前 Run 目录。

### ResearchCodeSandbox

用于科研统计代码。

限制：

- FrozenDataset 只读；
- 只能使用批准的软件依赖；
- 只写当前 ExecutionRun；
- 保存环境、随机种子和日志。

## 18.3 学生代码评价维度

```text
运行正确性
物理模型正确性
数值误差
边界条件
代码结构
可读性
调试次数
错误类型
修复路径
提示依赖
迁移能力
解释能力
```

## 18.4 版本字段

必须保存：

```text
rubric_version
unit_test_version
scoring_code_hash
error_classifier_version
```

## 18.5 学习过程事件

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

---

# 19. Feedback Firewall

## 19.1 流程

```text
学生代码
→ 错误诊断
→ 生成候选提示
→ Feedback Firewall
→ PASS：发送学生
→ FAIL：降级或重新生成
```

## 19.2 检查维度

```text
Correctness
PedagogicalValue
AnswerLeakageRisk
HallucinationRisk
LevelAppropriateness
SafetyRisk
Clarity
```

## 19.3 提示阶梯

```text
L1：反思性问题
L2：概念提示
L3：错误区域定位
L4：局部伪代码
L5：最小代码片段
```

默认从最低等级开始。

## 19.4 禁止内容

- 完整答案；
- 完整函数；
- 隐藏测试；
- 超出课程范围 API；
- 不存在的库；
- 危险命令；
- 隐私请求；
- 直接替学生完成任务。

---

# 20. 数据三层版本管理

## 20.1 RawDataset

特点：

- 原始上传；
- 只读；
- 不可覆盖；
- 保存 SHA256；
- 保存 Schema；
- 保存隐私检查状态。

## 20.2 ProcessedDataset

特点：

- 只能依据批准的 DataProcessingPlan 生成；
- 关联 RawDataset；
- 保存清洗代码和日志；
- 支持多个版本；
- 不允许直接成为正式结果来源。

## 20.3 FrozenDataset

特点：

- 正式分析版本；
- 只读；
- 不可修改；
- 保存数据哈希和 Schema 哈希；
- 所有正式 ExecutionRun 只能读取该版本。

## 20.4 DataFreezeRecord

建议字段：

```text
freeze_id
processed_dataset_id
frozen_dataset_id
dataset_sha256
schema_hash
requested_by = controller
executed_by = data_freeze_operator
operator_run_ref
approval_ref
created_at
```

---

# 21. 科研分析代码与统计执行

## 21.1 Codex 的角色

Codex 是可替换的 `CodingProvider`。

Codex 负责：

- 根据 CodeSpecification 生成代码；
- 修复代码；
- 生成测试；
- 提供运行说明。

Codex 不负责：

- 决定统计方法；
- 修改预注册计划；
- 选择性分析；
- 解释正式结果；
- 推进项目状态。

## 21.2 CodeSpecification

包含：

```text
executable_analysis_plan_id
frozen_dataset_id
frozen_schema_hash
required_outputs
execution_mode
sandbox_policy_ref
```

## 21.3 CodeReviewGate

检查：

- 代码是否读取正确 FrozenDataset；
- 是否修改输入数据；
- 是否与分析计划一致；
- 是否改变模型；
- 是否写死结果；
- 是否遗漏效应量和置信区间；
- 是否使用未批准依赖；
- 是否通过安全测试。

## 21.4 执行模式

### PYTHON_ONLY

用于：

- MVP；
- SPSS 不可用；
- 开发和测试。

只能声明：

> Python 单引擎真实执行并完成完整性验证。

### SPSS_PYTHON_DUAL

用于：

- SPSS 可用；
- 完整比赛版本；
- SPSS 主分析，Python 独立复核。

可以声明：

> SPSS 主分析经 Python 独立复核。

---

# 22. 结果验证与 StatisticalResultCard

## 22.1 ResultValidationReport

```text
validation_mode
execution_run_refs
input_validation
model_validation
numeric_validation
output_integrity_validation
consistency_report_ref
decision
failure_refs
created_at
```

## 22.2 四层验证

### 输入验证

```text
dataset_sha256
案例 ID 集合
样本量
变量类型
```

### 模型验证

```text
设计矩阵
参考组
缺失值策略
平方和类型
对比编码
随机效应结构
```

### 数值验证

```text
系数
标准误
自由度
统计量
p 值
效应量
置信区间
```

### 输出完整性验证

```text
必要表格
假设检查
稳健性分析
结果字段
运行日志
```

## 22.3 StatisticalResultCard 状态

```text
execution_status:
generated
execution_verified
cross_engine_verified

interpretation_status:
pending_human_review
human_approved
rejected
```

`PYTHON_ONLY` 不能达到 `cross_engine_verified`。

---

# 23. Atomic Claim 与论文写作

## 23.1 一个 Claim 只有一个类型

```text
LITERATURE
RESULT
METHOD
INTERPRETATION
SPECULATION
LIMITATION
```

禁止：

```text
RESULT + INTERPRETATION
```

## 23.2 复合句拆分

一个论文句子可以拆为多个 AtomicClaim。

示例：

原句：

> AI 支架组迁移成绩更高，这说明 AI 支架能够提高学生能力。

拆分为：

### RESULT Claim

> AI 支架组无 AI 迁移成绩高于对照组。

关联：

```text
StatisticalResultCard
ResultValidationReport
ExecutionRun
```

### INTERPRETATION Claim

> 该结果可能说明分层 AI 支架有助于学生形成独立建模能力。

关联：

```text
RESULT Claim
理论证据
解释边界
HumanApproval
```

## 23.3 ClaimRelation

```text
SUPPORTS
INTERPRETS
QUALIFIES
LIMITS
CONTRADICTS
DERIVED_FROM
```

---

# 24. 独立审稿机制

## 24.1 Citation Reviewer

检查：

- 文献是否真实；
- 原文是否可定位；
- 主张与来源是否一致；
- 是否存在错误引用；
- 是否遗漏反向证据。

## 24.2 Method Reviewer

检查：

- 研究问题与设计匹配；
- Estimand；
- CausalDAG；
- 样本；
- 统计模型；
- 混淆；
- 预注册一致性；
- 因果边界。

## 24.3 Reproducibility Reviewer

检查：

- 数据版本；
- 代码；
- 环境；
- 运行；
- 输出；
- 哈希；
- 复现包。

## 24.4 Pedagogy Reviewer

检查：

- STEM 任务；
- Rubric；
- 教学目标；
- 提示；
- 答案泄漏；
- 学习效果；
- 迁移能力；
- 干预忠实度。

## 24.5 Review Arbiter

合并 Reviewer 结果，去除重复问题，按严重程度排序。

---

# 25. 全链路科研溯源

## 25.1 AgentRunRecord

```text
agent_run_id
agent_id
agent_version
prompt_template_version
input_artifact_refs
output_artifact_refs
tool_run_refs
reviewer_feedback_refs
route_decision_ref
started_at
finished_at
```

## 25.2 主要边

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

## 25.3 WorkflowSignature

由以下哈希组合：

```text
研究协议哈希
数据哈希
代码哈希
环境哈希
执行输出哈希
```

## 25.4 论文句子反向追溯

```text
论文句子
→ ClaimSegment
→ AtomicClaim
→ StatisticalResultCard
→ ResultValidationReport
→ ExecutionRun
→ CodeArtifact
→ CodeSpecification
→ ExecutableAnalysisPlan
→ PreregisteredAnalysisPlan
→ FrozenDataset
→ StudyProtocol
→ ResearchQuestion
→ ApprovalRecord
```

---

# 26. 教育研究复现审计模式

## 26.1 输入

```text
论文 PDF
CSV / Excel / SAV 数据
Python / R 代码
SPSS Syntax
补充材料
```

## 26.2 检查

```text
论文样本量与数据是否一致
变量定义是否一致
代码能否运行
表格数字能否重现
p 值能否重现
效应量能否计算
排除规则是否完整
选择性报告
结论是否超过结果
```

## 26.3 输出状态

```text
FULLY_REPRODUCIBLE
PARTIALLY_REPRODUCIBLE
NOT_REPRODUCIBLE
INSUFFICIENT_MATERIALS
```

## 26.4 输出

```text
ReproductionAuditReport
```

---

# 27. 核心数据结构

## 27.1 VersionedEntity

```python
class VersionedEntity:
    id: str
    version: int
    schema_version: str
    created_at: datetime
    created_by: str
    supersedes_ref: str | None
```

## 27.2 ApprovalRecord

```python
class ApprovalRecord:
    approval_id: str
    artifact_id: str
    artifact_version: int
    decision: str
    decided_by: str
    decided_at: datetime
    reason: str | None
    risk_acknowledgements: list[str]
    previous_approval_ref: str | None
```

## 27.3 GateResult

```text
gate_id
gate_version
artifact_id
decision
decision_scope
blocked_target_ids
research_test_result_refs
risk_profile_ref
missing_fields
risk_flags
next_action
created_at
```

## 27.4 RouteDecision

```text
decision_id
current_stage
selected_route
decision_scope
blocked_target_ids
gate_result_refs
risk_profile_ref
budget_snapshot_ref
triggered_rules
final_decider
policy_version
created_at
```

## 27.5 RiskProfile

```text
artifact_id
method_risk
citation_risk
pedagogy_risk
privacy_risk
reproducibility_risk
causal_overclaim_risk
answer_leakage_risk
overall_level
triggered_rules
```

## 27.6 ResearchTestResult

```text
test_id
artifact_id
status
severity
evidence_refs
failure_reason
repair_action
executed_at
```

## 27.7 AtomicClaim

```text
claim_id
segment_ref
claim_type
claim_text
evidence_refs
verification_status
artifact_status
```

---

# 28. ResearchState 与存储分层

## 28.1 ResearchState

只保存：

```text
current_stage
task_status
task_ledger
progress_ledger
evidence_ledger
artifact_refs
data_asset_refs
execution_run_refs
protocol_refs
research_test_result_refs
risk_profile_refs
route_decision_refs
agent_run_refs
approval_request_refs
budget_state
recent_rounds
short_memory_summary
long_memory_refs
risk_flags
error_log
```

## 28.2 三本账本

### TaskLedger

保存：

- 项目目标；
- 范围；
- 事实；
- 未决问题；
- 当前计划；
- 下一步。

### ProgressLedger

保存：

- 负责人；
- 工具；
- 进度；
- 耗时；
- 成本；
- 失败；
- 阻塞。

### EvidenceLedger

保存：

- 主张；
- 支持证据；
- 冲突证据；
- 原文位置；
- 来源；
- 核验状态。

## 28.3 四类 Store

### SourceEvidenceStore

保存文献、理论、量表和原文证据。

### ArtifactStore

保存：

- 代码；
- 数据；
- 表格；
- 图形；
- SPSS 输出；
- 论文；
- PPT；
- 报告。

### DecisionStore

保存人工审批和正式科研决定。

### ExecutionStore

保存：

- 运行环境；
- 软件版本；
- 参数；
- 随机种子；
- 日志；
- 错误；
- 输出引用。

---

# 29. 安全、隐私、伦理与科研诚信

## 29.1 硬阻塞规则

以下情况不交给模型自由判断，直接阻塞对应作用域：

```text
未脱敏个人数据
虚假正式文献
RawDataset 被覆盖
FrozenDataset 哈希异常
正式代码读取错误数据版本
学生代码访问网络或宿主文件
正式结果缺少 ExecutionRun
论文数字无法追溯
双引擎使用不同案例集合
缺少合法数据或伦理许可
```

## 29.2 沙箱限制

```text
禁止网络
禁止任意 shell
禁止系统命令
禁止特权操作
限制 CPU
限制内存
限制运行时间
限制子进程
环境变量白名单
禁止运行时安装依赖
FrozenDataset 只读
只写当前 Run 目录
```

## 29.3 AI 标识

系统生成内容必须标记：

```text
AI-generated
AI-assisted
human-approved
source-verified
execution-verified
```

## 29.4 未成年人和学生数据

如涉及学生数据：

- 必须脱敏；
- 必须明确授权；
- 不保存姓名、学号等直接标识；
- 使用匿名 ID；
- 控制访问权限；
- 遵循学校伦理审批要求；
- 未通过隐私检查不得进入模型。

---

# 30. 项目目录结构

```text
src/
├── core/
│   ├── models.py
│   ├── state.py
│   ├── enums.py
│   ├── ledgers.py
│   ├── claims.py
│   ├── events.py
│   └── reducers.py
│
├── controller/
│   ├── workflow.py
│   ├── merger.py
│   ├── router.py
│   ├── approvals.py
│   ├── data_freeze_service.py
│   ├── error_handler.py
│   ├── policy/
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
├── agents/
│   ├── contracts.py
│   ├── tutor_agent.py
│   ├── evidence_agent.py
│   ├── design_agent.py
│   ├── analysis_agent.py
│   ├── writer_agent.py
│   └── reviewer_agent.py
│
├── research_protocol/
│   ├── models.py
│   ├── compiler.py
│   ├── feasibility.py
│   ├── estimand.py
│   ├── causal_dag.py
│   ├── preregistration.py
│   └── candidate_search.py
│
├── operators/
│   ├── models.py
│   ├── registry.py
│   ├── literature/
│   ├── research_data/
│   ├── learner_code/
│   ├── feedback/
│   ├── coding/
│   ├── statistics/
│   ├── provenance/
│   └── verification/
│
├── graph_rag/
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── vector_store.py
│   ├── graph_store.py
│   ├── retriever.py
│   └── sync_manager.py
│
├── memory/
│   ├── short_memory.py
│   ├── long_memory.py
│   └── memory_manager.py
│
├── artifacts/
│   ├── models.py
│   ├── artifact_store.py
│   ├── decision_store.py
│   ├── execution_store.py
│   ├── version_manager.py
│   └── provenance.py
│
├── research_data/
│   ├── models.py
│   ├── ingestion.py
│   ├── data_dictionary.py
│   ├── audit.py
│   ├── privacy_check.py
│   ├── processing.py
│   └── freeze.py
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
├── coding/
│   ├── models.py
│   ├── provider.py
│   ├── codex_provider.py
│   ├── specifications.py
│   ├── code_reviewer.py
│   ├── sandbox.py
│   └── test_runner.py
│
├── statistics/
│   ├── models.py
│   ├── analysis_plan.py
│   ├── plan_compiler.py
│   ├── mode_policy.py
│   ├── spss_adapter.py
│   ├── python_adapter.py
│   ├── output_parser.py
│   ├── assumption_checks.py
│   ├── consistency_checker.py
│   └── result_card.py
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
├── reproduction_audit/
│   ├── models.py
│   ├── material_ingestion.py
│   ├── manuscript_parser.py
│   ├── replication_runner.py
│   ├── consistency_auditor.py
│   └── report_builder.py
│
├── executors/
│   ├── execution_manager.py
│   ├── run_manifest.py
│   ├── environment_capture.py
│   ├── resource_limits.py
│   └── sandbox_policy.py
│
├── evaluation/
│   ├── benchmark_cases/
│   ├── literature_eval/
│   ├── learner_code_eval/
│   ├── analysis_eval/
│   ├── writing_eval/
│   ├── workflow_ablation/
│   └── user_study/
│
├── api/
└── utils/
    ├── hash_utils.py
    ├── validators.py
    ├── ids.py
    └── logger.py
```

---

# 31. Phase 0—Phase 8 实施路线

## Phase 0：设计统一

### 状态

```text
已完成
```

### 内容

- 项目定位；
- 核心创新；
- 权限矩阵；
- 数据流程；
- 主 Demo；
- 状态机；
- 数据结构；
- Phase 1 范围。

---

## Phase 1：核心模型与状态安全

### 目标

建立系统骨架，不实现完整业务。

### 实现

```text
核心枚举
VersionedEntity
ApprovalRecord
ArtifactRef
ResearchState
AgentResult
OperatorSpec
ResearchTestResult
RiskProfile
RouteDecision
BudgetState
Reducer
Store 接口
Controller Merger
规则路由
不变量测试
```

### 不实现

- 真实 Codex；
- SPSS；
- GraphRAG；
- 学生沙箱；
- 六 Agent 完整逻辑；
- 前端。

---

## Phase 2：最小真实闭环

```text
上传学生代码
→ 自动测试
→ 评分
→ 合并数据
→ Raw / Processed / Frozen
→ PYTHON_ONLY 分析
→ StatisticalResultCard
→ AtomicClaim
→ 可追溯结果段
```

---

## Phase 3：科研单元测试与 Gate

实现：

- DataAuditGate；
- AnalysisPlanGate；
- CodeReviewGate；
- ResultValidationGate；
- ClaimEvidenceGate；
- ReleaseGate。

---

## Phase 4：STEM 实验和 Feedback Firewall

实现：

- ProgrammingTask；
- CodeRubric；
- UnitTestSpecification；
- TaskEquivalenceReport；
- HintPolicy；
- Feedback Firewall；
- 学习过程事件；
- 提示依赖；
- 无 AI 迁移评价。

---

## Phase 5：文献与研究协议编译

实现：

- SearchProtocol；
- PaperCard；
- EvidenceMatrix；
- ContradictionMap；
- NoveltyReport；
- Research Protocol Compiler；
- Estimand；
- CausalDAG；
- PowerAnalysis；
- Preregistration。

---

## Phase 6：Codex、SPSS 和双轨分析

实现：

- CodingProvider；
- CodexProvider；
- SPSSAdapter；
- PythonAdapter；
- ConsistencyChecker；
- 双轨结果验证。

---

## Phase 7：风险动态路由和 Reviewer

实现：

- 风险评分；
- 动态 Reviewer；
- 预算控制；
- RouteDecision；
- 多轮修订控制；
- 停滞检测。

---

## Phase 8：完整产品和比赛材料

实现：

- 写作；
- 复现审计；
- 溯源界面；
- 前端；
- 用户测试；
- 效果验证；
- 比赛 Demo；
- PPT、视频和申报材料。

---

# 32. Phase 1 当前开发范围

## 32.1 最小文件

```text
src/core/
src/controller/
src/artifacts/
src/research_protocol/models.py
src/research_data/models.py
src/coding/models.py
src/statistics/models.py
src/statistics/mode_policy.py
src/agents/contracts.py
src/operators/models.py
src/operators/registry.py
src/verification/models.py
src/verification/rubric_registry.py
src/verification/test_runner.py
src/provenance/models.py
src/provenance/workflow_signature.py
src/utils/
tests/
```

## 32.2 实施顺序

```text
A. enums 与基础模型
B. VersionedEntity、ApprovalRecord 和引用模型
C. ResearchState 与 Reducer
D. AgentResult 和 Operator 契约
E. Store 接口
F. Controller Merger 和 Rule Router
G. Verification 接口
H. 不变量测试
```

## 32.3 Phase 1 验收

- Agent 无法改阶段；
- State 不保存大对象；
- ExecutionRun 只能引用 FrozenDataset；
- AtomicClaim 只有一个类型；
- PYTHON_ONLY 不能标记 cross_engine_verified；
- 局部 Run 错误不阻塞整个 Project；
- 未批准预注册计划不能进入正式数据采集；
- 重放审批不会产生重复副作用；
- Reducer 并行合并不会覆盖已有引用。

---

# 33. 自动化测试与不变量

建议测试目录：

```text
tests/
├── test_state_permissions.py
├── test_state_references_only.py
├── test_dataset_invariants.py
├── test_analysis_mode_policy.py
├── test_atomic_claim.py
├── test_decision_scope.py
├── test_approval_invariants.py
├── test_reducer_behavior.py
├── test_versioning.py
└── test_idempotent_resume.py
```

## 核心测试

### Agent 越权测试

```text
AgentResult 修改 current_stage
→ 拒绝
```

### State 大对象测试

```text
将完整 PDF、代码或数据写入 State
→ 拒绝
```

### 数据版本测试

```text
ExecutionRun 引用 RawDataset
→ 拒绝

ExecutionRun 引用 ProcessedDataset
→ 拒绝

ExecutionRun 引用 FrozenDataset
→ 允许
```

### 分析模式测试

```text
PYTHON_ONLY + cross_engine_verified
→ 拒绝
```

### Claim 测试

```text
AtomicClaim 同时包含两个 claim_type
→ 拒绝
```

### 幂等测试

```text
同一审批 resume 两次
→ 不产生两个 FrozenDataset
```

---

# 34. 比赛 Demo 设计

## 34.1 Demo 核心要求

三分钟内展示：

```text
研究想法输入
→ 协议编译
→ 学生代码评价
→ 数据冻结
→ Python 分析
→ 结果卡
→ 论文主张追溯
```

## 34.2 推荐 Demo 画面

### 画面 1：研究协议编译

输入：

> 研究 AI 分层提示对师范生 Python 物理建模能力的影响。

输出：

```text
ResearchQuestion
Estimand
StudyProtocol
ProgrammingTask
PreregisteredAnalysisPlan
```

### 画面 2：科研单元测试

```text
总测试：42
通过：36
警告：4
失败：2
```

显示：

- 缺少功效分析；
- 主要结果变量不唯一。

### 画面 3：Feedback Firewall

候选提示：

> 直接使用下面的完整函数……

结果：

```text
AnswerLeakageRisk = HIGH
Decision = REJECT
```

重新生成概念提示。

### 画面 4：学生代码评价

显示：

- 单元测试；
- 物理模型；
- 错误类型；
- 提示次数；
- 迁移表现。

### 画面 5：数据冻结

显示：

```text
RawDataset SHA256
ProcessedDataset
FrozenDataset SHA256
ApprovalRecord
```

### 画面 6：真实分析

显示：

```text
PYTHON_ONLY
execution_verified
```

### 画面 7：论文句子追溯

点击论文数字，展示：

```text
AtomicClaim
→ ResultCard
→ ExecutionRun
→ Code
→ FrozenDataset
→ AnalysisPlan
```

---

# 35. 效果验证与评估方案

## 35.1 黄金案例 1：文献证据链

准备：

```text
20—50 篇 STEM 教育论文
```

指标：

```text
筛选 Precision
筛选 Recall
字段抽取准确率
原文定位率
虚假引用率
```

## 35.2 黄金案例 2：学生代码评价

准备：

```text
30—50 份 Python 物理建模代码
```

错误类型：

- 角度转换错误；
- 速度分解错误；
- 时间更新错误；
- 循环终止错误；
- 单位错误；
- 数值方法错误；
- 代码结构错误；
- 看似运行但模型错误。

指标：

```text
自动测试准确率
错误分类准确率
与教师评分一致性
答案泄漏率
迁移评价有效性
```

## 35.3 黄金案例 3：统计和写作复现

提供：

- 脱敏数据；
- 标准分析计划；
- 标准答案。

指标：

```text
代码执行成功率
样本量一致率
模型设置一致率
p 值准确率
效应量准确率
论文数字一致率
因果过度表述率
```

## 35.4 工作流消融

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
平均时间
平均成本
虚假引用率
统计错误率
```

## 35.5 用户测试

最低要求：

```text
1 名教育学或 STEM 教育教师
1 名教育学研究生
```

建议：

```text
10—15 人小规模使用
50 人以上分模块使用
```

---

# 36. 与评分标准的对应关系

## 36.1 作品完成度

证据：

- 真实闭环；
- 稳定状态机；
- 自动测试；
- 可恢复审批；
- 可运行 Demo；
- 完整材料。

## 36.2 创意实用度

创新：

- 研究协议编译；
- 学生代码与教学实验；
- 科研结果追溯；
- 双闭环。

## 36.3 技术实现度

技术：

- LangGraph；
- 六 Agent；
- Operator Registry；
- GraphRAG；
- 沙箱；
- Codex；
- SPSS / Python；
- Store；
- 溯源图。

## 36.4 技术先进性

技术亮点：

- 风险动态路由；
- 科研单元测试；
- Atomic Claim；
- Feedback Firewall；
- 全链路 Provenance；
- 复现审计。

## 36.5 内容质量度

证明：

- 黄金案例；
- 来源核验；
- 真实执行；
- 结果卡；
- 数字一致；
- 因果边界；
- 人工审批。

## 36.6 商业化潜力

目标产品：

- 高校教育学院科研工作台；
- STEM 教师发展平台；
- 教育研究方法教学系统；
- 学生代码评价 API；
- 科研复现审计服务。

## 36.7 用户认可度

准备：

- 真实用户身份；
- 使用时间；
- 使用频次；
- 任务完成情况；
- 前后对比；
- 用户反馈；
- 演示视频。

---

# 37. 团队分工建议

## 37.1 项目负责人 / 架构负责人

负责：

- 统一决策；
- 状态机；
- 权限边界；
- 进度管理；
- Codex 任务审核；
- 比赛材料统筹。

## 37.2 后端与流程控制负责人

负责：

- Pydantic 模型；
- ResearchState；
- Reducer；
- Controller；
- Store；
- API；
- 测试。

## 37.3 STEM 教育与研究设计负责人

负责：

- 主 Demo；
- StudyProtocol；
- 编程任务；
- Rubric；
- 教学提示；
- TaskEquivalence；
- 用户测试。

## 37.4 数据与统计负责人

负责：

- 数据字典；
- 数据审计；
- 数据冻结；
- 分析计划；
- Python；
- SPSS；
- 结果验证。

## 37.5 文献和知识库负责人

负责：

- 搜索协议；
- PaperCard；
- EvidenceMatrix；
- GraphRAG；
- 文献黄金集。

## 37.6 前端与展示负责人

负责：

- 项目工作台；
- 状态界面；
- Gate 面板；
- 溯源界面；
- Demo；
- 视频。

## 37.7 测试与比赛材料负责人

负责：

- 黄金案例；
- 自动化测试；
- 用户反馈；
- 效果验证报告；
- PPT；
- 技术报告；
- 演示脚本。

---

# 38. 里程碑与协作方式

## 38.1 每个阶段必须产出

```text
设计说明
数据结构
代码
自动化测试
验收记录
风险清单
下一阶段输入
```

## 38.2 Git 分支建议

```text
main
develop
feature/core-models
feature/controller
feature/data
feature/learner-code
feature/statistics
feature/graph-rag
feature/frontend
```

## 38.3 Pull Request 要求

每个 PR 必须说明：

- 解决的问题；
- 修改的文件；
- 设计依据；
- 测试；
- 是否改变数据结构；
- 是否改变状态机；
- 是否产生兼容性影响。

## 38.4 禁止事项

- 未讨论直接改核心状态；
- 未审批直接改 Schema；
- 删除历史工件；
- 覆盖 RawDataset；
- 在主进程执行学生代码；
- 将测试跳过后合并主分支。

---

# 39. 风险、过度设计与降级策略

## 39.1 范围过大

风险：

- 系统模块过多；
- 比赛周期有限；
- 每个模块都可能只做出界面。

对策：

```text
先最小闭环
再扩展文献
再扩展教学实验
再扩展双引擎
最后做动态路由
```

## 39.2 风险分数伪精确

第一版采用：

```text
硬规则
少量可解释阈值
专家校准
```

暂不使用机器学习自动风险预测。

## 39.3 Feedback Firewall 缺少标注数据

第一版：

- 规则检查；
- 教师人工标注；
- 少量专家测试。

不宣传“已达到专家水平”。

## 39.4 SPSS 无法部署

降级：

```text
PYTHON_ONLY
```

界面明确标识。

## 39.5 CodexProvider 无法直接集成

降级：

```text
MockCodingProvider
ManualCodingProvider
```

保持接口不变。

## 39.6 GraphRAG 来不及

降级：

```text
本地文献库
关键词 + 向量检索
PaperCard 手动核验
```

## 39.7 学生沙箱安全不足

比赛 Demo 可使用：

- 预先审核代码；
- Docker 隔离；
- 严格白名单；
- 不开放任意用户代码。

---

# 40. 当前未决事项

以下事项必须由负责人决定，队友和 Codex 不得自行假设。

## 40.1 数据

- 合法脱敏演示数据来源；
- 学生代码样本来源；
- 是否进行真实小规模实验；
- 是否使用模拟数据作为非正式 Demo。

## 40.2 SPSS

- 许可证；
- 安装节点；
- 非 GUI 调用；
- 比赛部署方式；
- 数值容差。

## 40.3 Codex

- 鉴权；
- 服务形态；
- 可访问工作目录；
- 网络权限；
- 调用限制。

## 40.4 存储

- PostgreSQL 或 SQLite；
- 本地文件还是对象存储；
- 备份；
- 权限；
- 版本保留。

## 40.5 人工审批

- 审批角色；
- 审批权限；
- 教师和研究生权限差异；
- 伦理责任归属。

## 40.6 算法阈值

- Gate 阈值；
- 风险阈值；
- AnswerLeakageRisk；
- Rubric 权重；
- 任务等值标准；
- SPSS/Python 容差。

---

# 41. 接下来两周的执行清单

## 第一周：Phase 1 核心类型

### 任务

1. 建立项目目录；
2. 建立枚举；
3. 实现 VersionedEntity；
4. 实现 ApprovalRecord；
5. 实现 ArtifactRef；
6. 实现 ResearchState；
7. 实现 AgentResult；
8. 实现 OperatorSpec；
9. 实现 RouteDecision；
10. 实现 GateResult；
11. 实现 RiskProfile；
12. 实现 BudgetState；
13. 实现 Reducer；
14. 编写基础测试。

### 验收

```text
pytest 全部通过
mypy / pyright 基础检查通过
模型序列化通过
非法状态被拒绝
```

## 第二周：Controller 骨架和 Store

### 任务

1. Controller Merger；
2. Rule Router；
3. Approval interrupt/resume；
4. ArtifactStore 接口；
5. DecisionStore 接口；
6. ExecutionStore 接口；
7. Operator Registry；
8. WorkflowSignature；
9. 幂等测试；
10. 并行 Reducer 测试。

### 输出

```text
Phase 1 技术报告
文件清单
测试报告
设计冲突清单
Phase 2 输入
```

---

# 42. 术语表

| 术语 | 含义 |
|---|---|
| Research Protocol Compiler | 将自然语言想法编译为结构化科研协议 |
| Controller | 唯一改变项目阶段的流程控制器 |
| Agent | 负责专业推理但不直接控制流程 |
| Operator | 执行确定性工具操作 |
| Gate | 根据测试、风险和审批决定是否通过 |
| Research Unit Test | 对科研工件执行具体检查 |
| Risk Engine | 汇总风险并形成 RiskProfile |
| Reviewer | 对高风险或复杂问题进行专业审查 |
| Human Approval | 人类对高影响科研事项作最终决定 |
| RawDataset | 原始只读数据 |
| ProcessedDataset | 经批准处理的数据 |
| FrozenDataset | 正式分析只读数据 |
| PreregisteredAnalysisPlan | 数据采集前批准并冻结的分析计划 |
| ExecutableAnalysisPlan | 根据 FrozenDataset Schema 编译的执行计划 |
| AtomicClaim | 单一类型、可追溯的最小科研主张 |
| StatisticalResultCard | 结构化正式统计结果 |
| WorkflowSignature | 协议、数据、代码、环境和输出的组合签名 |
| Feedback Firewall | AI 教学提示发送前的质量与安全检查 |
| Provenance Graph | Agent、证据、执行和主张的追溯图 |
| PYTHON_ONLY | Python 单引擎真实执行 |
| SPSS_PYTHON_DUAL | SPSS 主分析加 Python 独立复核 |

---

# 43. 最终统一表述

> STEM-SCI 面向教育学一流学科建设，聚焦 STEM 编程教育实验研究，通过教育研究协议编译器，将研究者的自然语言构想转化为文献检索、研究设计、编程任务、教学支架、数据采集和统计分析等可执行科研协议。系统采用风险与不确定性感知的动态流程控制，协调六类专业 Agent 和确定性 Operator，并通过科研单元测试、学生代码评价、教学反馈防火墙、Raw—Processed—Frozen 数据链、Codex—SPSS—Python 可复现分析以及 Agent—证据—执行—主张溯源图，对科研全过程实施质量控制。最终形成从文献证据、学生学习过程和科研数据，到统计结果、论文主张和复现包的完整可追溯闭环。

---

# 附录 A：团队必须共同遵守的十条规则

1. Controller 是唯一可修改 `current_stage` 的组件。  
2. Agent 只能返回结构化候选结果。  
3. 正式数据分析只能读取 FrozenDataset。  
4. PreregisteredAnalysisPlan 必须在数据采集和结果查看前批准。  
5. Codex 不是科研决策者。  
6. PYTHON_ONLY 不能宣称双引擎复核。  
7. 一个 AtomicClaim 只能有一个 claim_type。  
8. 未核验文献不能支持正式结论。  
9. 学生代码和科研代码必须在不同沙箱运行。  
10. 没有真实 ExecutionRun 的数字不得进入正式论文。  

---

# 附录 B：当前项目状态

```text
Phase 0：PASSED
Phase 1：READY
```

当前允许：

```text
核心模型
状态安全
权限契约
Store 接口
Controller 骨架
自动化不变量测试
```

当前禁止提前实施：

```text
完整六 Agent
真实 CodexProvider
SPSS 自动化
完整 GraphRAG
真实开放学生沙箱
Feedback Firewall 学习模型
在线自动工作流搜索
完整前端
自动投稿
```
