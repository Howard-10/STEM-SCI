# STEM-SCI 项目背景说明（供 Codex 开发使用）

> 文档用途：作为 Codex 开发本项目时的统一背景、架构约束与当前决策说明。  
> 项目当前阶段：总体方案设计、底层模块规划与科研计算模块补充阶段。  
> 学科方向：教育学中的 STEM 教育。  
> 应用场景：面向 STEM 教育研究的 SCI/SSCI 科研协作与助研系统。  
> 当前日期：2026-07-23。

---

# 一、项目定位

## 1.1 项目名称

**STEM-SCI：面向 STEM 教育研究的可追溯多 Agent 科研协作系统**

## 1.2 项目目标

项目不是做一个普通的教育学问答机器人，也不是宣传“六个 Agent 全自动完成一篇 SCI 论文”。

项目目标是：

> 通过一个确定性科研流程控制器，协调多个专业 Agent 和真实科研工具，辅助 STEM 教育研究者完成选题、文献检索、证据综合、研究设计、数据审计、统计分析、论文写作和独立审稿，并保证关键证据可追溯、数据分析可复现、流程状态可检查、关键科研决策由研究者确认。

## 1.3 学科与应用边界

- 一级学科场景：教育学。
- 垂直方向：STEM 教育。
- 主要研究主题：
  - STEM 项目式学习；
  - STEM 探究式学习；
  - 生成式 AI 与 STEM 教育；
  - STEM 学习中的复杂问题解决；
  - STEM 学习中的认知负荷；
  - STEM 教师教育；
  - STEM 计算思维；
  - STEM 学习评价；
  - 虚拟实验、机器人、编程教育。
- 主要成果形式：
  - SCI/SSCI 论文；
  - 文献综述；
  - 研究方案；
  - 数据分析报告；
  - 代码和复现包；
  - PPT 与比赛演示材料。

---

# 二、比赛背景与项目价值

本项目对应“面向一流学科建设的学科垂类大模型与创新应用开发”赛题。

赛题要求开发面向特定学科的垂类大模型或智能体应用，并解决真实教学或科研场景中的问题。

本项目重点对应以下赛题要求：

- 学科专业知识库；
- 检索增强生成 RAG；
- 多步骤、带条件分支的复杂工作流；
- 教育科研数据分析；
- 学术写作辅助；
- 内容可追溯；
- 复杂问题求解；
- 个性化与自适应；
- 至少三个典型测试任务；
- 至少两名真实目标用户试用反馈；
- 提供可运行 Demo、代码、技术方案和效果验证报告。

---

# 三、演示用 STEM 教育研究案例

系统第一版应使用一个具体案例贯穿全部流程，避免做成“任何教育学课题都能研究”的泛化工具。

推荐演示案例：

> 生成式 AI 支架对师范生 STEM 项目式学习中复杂问题解决能力和认知负荷的影响：一项准实验混合研究。

该案例只作为系统演示背景，不代表系统可以提前生成研究结果。

系统需要围绕该案例依次产出：

1. `ResearchContract`
2. `ResearchQuestionTree`
3. `SearchProtocol`
4. `PRISMALedger`
5. `PaperCard`
6. `EvidenceMatrix`
7. `ContradictionMap`
8. `ResearchGapReport`
9. `StudyProtocol`
10. `VariableDictionary`
11. `InstrumentPlan`
12. `SamplingPlan`
13. `AnalysisPlan`
14. `EthicsChecklist`
15. `DataAuditReport`
16. `AnalysisCode`
17. `RunManifest`
18. `StatisticalResultCard`
19. `RobustnessChecks`
20. `ClaimEvidenceMap`
21. `ManuscriptDraft`
22. `ReviewReport`
23. `ReproducibilityBundle`

---

# 四、总体架构原则

## 4.1 核心原则

本项目不采用：

- 六个 Agent 自由聊天；
- 六个 Agent 固定串行排队；
- Agent 自行宣布阶段完成；
- Agent 自行修改科研结论；
- Agent 自行修改统计数字；
- 大模型直接“心算”统计结果；
- 没有人工确认的全自动论文生成。

本项目采用：

> 一个确定性科研流程控制器 + 六类按需调用的专业 Agent + 三本共享账本 + 科研工件系统 + 工件级质量闸门 + 关键节点人工审批 + 可复现科研计算工具。

## 4.2 分层架构

建议系统分为六层：

1. 用户交互层；
2. 科研流程控制层；
3. 六类专业 Agent 层；
4. 科研工件与三本账本层；
5. GraphRAG 与 Memory 底座；
6. 科研数据、代码执行与统计工具层。

---

# 五、六类专业 Agent

## 5.1 导师规划 Agent

职责：

- 将模糊想法转化为可执行研究计划；
- 建立研究问题树；
- 提出候选理论框架；
- 明确项目范围和不做什么；
- 输出项目路线图。

主要产物：

- `ResearchContract`
- `ResearchQuestionTree`
- `TheoryFramework`
- `ProjectRoadmap`

限制：

- 不得凭空生成研究结论；
- 不得擅自改变已确认研究范围。

## 5.2 证据综述 Agent

职责：

- 检索式设计；
- 文献检索；
- 去重；
- 标题摘要筛选；
- 全文筛选；
- 结构化证据抽取；
- 证据综合；
- 冲突证据分析；
- 研究空白识别。

主要产物：

- `SearchProtocol`
- `PRISMALedger`
- `PaperCard`
- `EvidenceMatrix`
- `ContradictionMap`
- `ResearchGapReport`

要求：

- 所有样本量、效应量、显著性结果和结论必须能回到论文原文位置；
- 筛选使用 `INCLUDE / EXCLUDE / UNCERTAIN` 三值决策；
- 不确定、高影响和最终纳入论文需要重点核验。

## 5.3 研究设计 Agent

职责：

- 根据研究问题生成 DBR、准实验、混合研究等方案；
- 定义变量和操作化；
- 设计抽样、分组、干预、测量和分析计划；
- 识别混淆变量和替代解释；
- 生成伦理方案。

主要产物：

- `StudyProtocol`
- `VariableDictionary`
- `InstrumentPlan`
- `SamplingPlan`
- `AnalysisPlan`
- `EthicsChecklist`

限制：

- 研究设计与统计分析计划必须经人工确认；
- 冻结后不得被数据分析 Agent 擅自修改。

## 5.4 科研计算与数据分析 Agent

原“数据分析 Agent”升级为：

> 科研计算与数据分析 Agent

内部包含：

- 数据审计；
- 分析计划编译；
- Codex 代码生成与调试；
- SPSS 正式分析；
- Python 独立复核；
- 统计假设检查；
- 结果一致性检查；
- 结果结构化解释；
- 可复现包生成。

主要产物：

- `DataAuditReport`
- `DataDictionary`
- `FrozenDataset`
- `AnalysisCode`
- `SPSSSyntax`
- `PythonVerificationCode`
- `RunManifest`
- `ExecutionRun`
- `StatisticalResultCard`
- `ResultConsistencyReport`
- `RobustnessChecks`
- `ReproducibilityBundle`

限制：

- 只能读取冻结后的数据；
- 必须按照已批准的 `AnalysisPlan` 执行；
- 计划外分析必须标记为探索性分析；
- 不得覆盖原始数据和原始统计输出；
- 不得擅自改变统计方法、变量角色和异常值处理策略。

## 5.5 论文写作 Agent

职责：

- 根据已核验的证据、研究设计和统计结果写作；
- 生成论文、摘要、PPT 和汇报稿；
- 建立主张—证据映射。

主要产物：

- `ClaimEvidenceMap`
- `ManuscriptDraft`
- `Abstract`
- `PPTOutline`
- `DemoNarrative`

限制：

- 不得创造新事实；
- 不得新增不存在的文献；
- 不得新增未执行的统计分析；
- 不得修改统计数字；
- 不得隐藏不显著结果。

## 5.6 独立审稿 Agent

职责：

- 只读审查整个项目；
- 检查引用、方法、统计、伦理和表述；
- 检查数据泄漏、混淆变量和选择性报告；
- 检查是否将相关性写成因果性；
- 检查论文、PPT、摘要和演示中的数字一致性。

限制：

- 不参与前期写作；
- 不允许“自己写、自己审”。

---

# 六、Agent 协作方式

## 6.1 严格顺序任务

例如：

- 根据批准的研究问题形成理论框架；
- 根据正式统计结果解释研究发现。

处理方式：

- 由一个最合适的 Agent 连续完成；
- 完成后交 Reviewer 检查；
- 不进行无意义的多 Agent 自由讨论。

## 6.2 可并行任务

例如：

- 多数据库文献检索；
- 多篇论文结构化抽取；
- 多主题证据整理。

处理方式：

- 同类 Worker 并行；
- 每个 Worker 处理明确分片；
- 由中央控制器去重、合并和检查冲突。

## 6.3 争议任务

例如：

- 不同研究对 AI 支架效果结论相反。

处理方式：

- 支持证据 Worker；
- 反向证据 Worker；
- 方法比较 Worker；
- 最多两轮定向辩论；
- 保留分歧及原因，不强行形成一致结论。

## 6.4 写作与审稿

```text
写作 Agent 生成草稿
→ 独立审稿 Agent 提出问题
→ 写作 Agent 定向修订
→ 最多自动往返三轮
→ 仍有争议时交给研究者
```

---

# 七、三本共享账本

## 7.1 任务账本 `task_ledger`

记录：

- 当前研究目标；
- 当前研究范围；
- 已确认事实；
- 未解决问题；
- 当前执行计划；
- 下一步动作。

## 7.2 进度账本 `progress_ledger`

记录：

- 当前任务负责人；
- 已完成任务；
- 未完成任务；
- 调用模型和工具；
- 时间；
- 费用；
- 失败次数；
- 重试次数；
- 阻塞原因。

## 7.3 证据账本 `evidence_ledger`

记录：

- 每一个科研主张；
- 支持该主张的论文或数据；
- 冲突证据；
- 原文位置；
- 来源状态；
- 核验状态；
- 人工确认状态。

---

# 八、科研工件系统

当前项目不能只把所有内容放入 `ResearchState`。

需要新增科研工件系统，`ResearchState` 只保存工件引用，不保存大文件全文。

## 8.1 ArtifactRef

```python
class ArtifactRef(TypedDict):
    artifact_id: str
    artifact_type: str
    version: int
    storage_uri: str
    sha256: str
    created_by: str
    verify_status: str
    created_at: str
```

工件类型示例：

- 文献矩阵；
- PRISMA；
- 研究方案；
- 数据审计报告；
- 数据文件；
- Python 代码；
- R 代码；
- SPSS Syntax；
- SPSS 输出；
- 图表；
- 论文版本；
- 审稿报告；
- 运行日志。

---

# 九、GraphRAG 与 Memory 当前底座

当前已有两份底层设计文档。

## 9.1 文件一

原文件：

`b2e1560f-a64d-4fb2-bb86-99cef2428606.md`

当前内容：

- `src/` 目录结构；
- `core/`；
- `graph_rag/`；
- `memory/`；
- `controller/`；
- `api/`；
- `agents/`；
- `utils/`；
- 依赖关系；
- 数据流；
- requirements；
- 团队接口约定。

建议改名：

`docs/development/module_contract.md`

定位：

> STEM-SCI 底层模块目录与接口契约。

## 9.2 文件二

原文件：

`fc703d91-1a64-48ff-b68a-8d7b325057c2.txt`

当前内容：

- GraphRAG；
- 双层知识库；
- ResearchState；
- 三本账本；
- 分层短期记忆；
- 长期项目记忆；
- LangGraph 状态机；
- 人工审批；
- 返工与阻塞；
- Agent 权限矩阵；
- 论文增量同步；
- PostgreSQL / Chroma / Neo4j。

建议改名：

`docs/architecture/technical_architecture.md`

定位：

> STEM-SCI 底层知识、记忆与流程控制技术方案。

注意：

这两个文件目前只能作为“底座方案”，还不是完整项目终稿。

---

# 十、当前底座目录结构

原目录大致为：

```text
src/
├── core/
│   ├── state.py
│   ├── models.py
│   ├── config.py
│   └── constants.py
├── graph_rag/
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── entity_extract.py
│   ├── vector_store.py
│   ├── graph_store.py
│   ├── retriever.py
│   ├── sync_manager.py
│   └── knowledge_base.py
├── memory/
│   ├── short_memory.py
│   ├── long_memory.py
│   ├── memory_manager.py
│   └── summary_llm.py
├── controller/
│   ├── workflow.py
│   ├── router.py
│   ├── gates.py
│   ├── error_handler.py
│   └── scheduler.py
├── api/
│   ├── rag_api.py
│   ├── memory_api.py
│   ├── state_api.py
│   └── sync_api.py
├── agents/
│   └── agent_specs.py
├── utils/
│   ├── hash_utils.py
│   ├── validators.py
│   └── logger.py
└── data/
    ├── base_literature/
    └── prompts/
```

---

# 十一、需要新增的目录

为接入 Codex、SPSS、数据审计和科研工件，需要扩展为：

```text
src/
├── core/
├── graph_rag/
├── memory/
├── controller/
├── agents/
│   ├── tutor_agent.py
│   ├── evidence_agent.py
│   ├── design_agent.py
│   ├── analysis_agent.py
│   ├── writer_agent.py
│   └── reviewer_agent.py
│
├── artifacts/
│   ├── models.py
│   ├── artifact_store.py
│   ├── version_manager.py
│   └── provenance.py
│
├── research_data/
│   ├── ingestion.py
│   ├── data_dictionary.py
│   ├── audit.py
│   ├── privacy_check.py
│   └── freeze.py
│
├── coding/
│   ├── provider.py
│   ├── codex_provider.py
│   ├── prompt_builder.py
│   ├── code_reviewer.py
│   ├── sandbox.py
│   └── test_runner.py
│
├── statistics/
│   ├── analysis_plan.py
│   ├── plan_compiler.py
│   ├── spss_adapter.py
│   ├── python_adapter.py
│   ├── output_parser.py
│   ├── assumption_checks.py
│   ├── consistency_checker.py
│   └── result_card.py
│
├── executors/
│   ├── execution_manager.py
│   ├── run_manifest.py
│   ├── environment_capture.py
│   └── resource_limits.py
│
├── api/
│   ├── rag_api.py
│   ├── memory_api.py
│   ├── state_api.py
│   ├── sync_api.py
│   ├── data_api.py
│   ├── coding_api.py
│   ├── analysis_api.py
│   └── artifact_api.py
│
└── utils/
```

---

# 十二、Codex 接入设计

## 12.1 Codex 的角色

Codex 只作为代码工程工具，不作为科研决策者。

Codex 负责：

- 生成 Python 数据清洗代码；
- 生成 R 代码；
- 生成 SPSS Syntax；
- 生成统计假设检查代码；
- 生成图表代码；
- 生成测试代码；
- 调试运行错误；
- 根据代码审查意见修改代码；
- 生成运行说明和依赖说明。

Codex 不负责：

- 决定应该使用什么统计方法；
- 决定哪个变量作为协变量；
- 决定是否删除异常值；
- 修改研究假设；
- 修改研究问题；
- 将探索性分析写成验证性分析；
- 自动解释结果是否支持理论。

## 12.2 CodingProvider 接口

不要把项目绑定到用户个人电脑的 Codex 客户端。

建议定义统一接口：

```python
class CodingProvider(Protocol):
    def generate_code(
        self,
        specification: CodeSpecification,
        workspace: WorkspaceRef
    ) -> CodeArtifact:
        ...

    def revise_code(
        self,
        code: CodeArtifact,
        review: CodeReview
    ) -> CodeArtifact:
        ...
```

第一版实现：

```text
CodexProvider
```

以后可以替换为其他代码模型。

---

# 十三、SPSS 接入设计

SPSS 不应该通过界面自动点击作为核心方案。

推荐流程：

```text
已批准 AnalysisPlan
→ Codex 生成 SPSS Syntax
→ 代码和方法审核
→ SPSS 执行 Syntax
→ 导出 SPSS 输出
→ 解析统计表
→ Python 独立复核
→ 结果一致性检查
→ 生成 StatisticalResultCard
```

SPSS 负责正式统计执行：

- 描述性统计；
- 信度分析；
- t 检验；
- 方差分析；
- ANCOVA；
- 回归；
- 中介和调节；
- 重复测量；
- 混合模型；
- 非参数检验；
- 因子分析等。

SPSS 不是大模型，不负责自动撰写科研结论。

## 13.1 SPSSAdapter

```python
class SPSSAdapter:
    def validate_installation(self) -> SPSSHealthCheck:
        ...

    def execute_syntax(
        self,
        syntax_artifact: ArtifactRef,
        frozen_dataset: DataAssetRef,
        run_config: RunConfig
    ) -> ExecutionRun:
        ...

    def export_output(
        self,
        run_id: str
    ) -> list[ArtifactRef]:
        ...

    def parse_output(
        self,
        output_artifacts: list[ArtifactRef]
    ) -> StatisticalResult:
        ...
```

注意：

- SPSS 依赖实际安装和许可；
- 不能只通过 `pip install` 完成；
- 第一版需要设计 SPSS 不可用时的降级方案；
- 可降级为 Python `statsmodels/scipy/pingouin`；
- 正式比赛演示可使用已部署 SPSS 的指定执行节点。

---

# 十四、双轨分析设计

推荐：

> SPSS 主分析 + Python 独立复核。

示例：

```text
SPSS 计算：
- 样本量
- 调整均值
- F 值
- p 值
- 偏 eta 平方

Python 复核：
- 样本量
- 描述统计
- 模型系数
- p 值
- 效应量
- 置信区间
```

系统生成：

`ResultConsistencyReport`

字段示例：

```python
class ResultConsistencyReport(TypedDict):
    report_id: str
    spss_run_id: str
    python_run_id: str
    compared_metrics: dict
    tolerance_rules: dict
    consistency_status: str
    conflicts: list[dict]
```

当关键结果超出容差时：

```text
BLOCKED
```

不能进入论文写作阶段。

---

# 十五、数据分析子流程

建议将科研计算设计为 LangGraph Subgraph。

```text
STUDY_PROTOCOL_APPROVED
→ DATA_INGESTED
→ DATA_AUDITED
→ 人工处理隐私、缺失值和异常值决策
→ DATA_FROZEN
→ ANALYSIS_PLAN_APPROVED
→ Codex 生成代码
→ CODE_REVIEWED
→ SPSS_EXECUTED
→ PYTHON_VERIFIED
→ RESULT_CONSISTENCY_CHECKED
→ STATISTICAL_RESULT_APPROVED
→ ANALYZED
```

---

# 十六、核心数据结构

## 16.1 DataAsset

```python
class DataAsset(TypedDict):
    data_id: str
    version: int
    original_filename: str
    storage_uri: str
    file_format: str
    sha256: str
    row_count: int
    column_count: int
    privacy_status: str
    freeze_status: str
    frozen_at: str | None
```

## 16.2 AnalysisPlan

```python
class AnalysisPlan(TypedDict):
    plan_id: str
    research_question_id: str
    hypothesis_id: str
    method: str
    dependent_variables: list[str]
    independent_variables: list[str]
    covariates: list[str]
    assumptions: list[str]
    effect_sizes: list[str]
    alpha: float
    missing_data_strategy: str
    outlier_strategy: str
    analysis_type: str
    approval_status: str
```

## 16.3 CodeArtifact

```python
class CodeArtifact(TypedDict):
    code_id: str
    language: str
    purpose: str
    source_model: str
    analysis_plan_id: str
    content_uri: str
    sha256: str
    version: int
    review_status: str
```

## 16.4 ExecutionRun

```python
class ExecutionRun(TypedDict):
    run_id: str
    code_id: str
    data_id: str
    executor: str
    software_version: str
    environment: dict
    random_seed: int | None
    started_at: str
    finished_at: str
    exit_code: int
    log_uri: str
    output_artifact_ids: list[str]
```

## 16.5 StatisticalResultCard

```python
class StatisticalResultCard(TypedDict):
    result_id: str
    analysis_plan_id: str
    execution_run_ids: list[str]
    method: str
    sample_size: int
    statistics: dict
    p_values: dict
    effect_sizes: dict
    confidence_intervals: dict
    assumption_checks: dict
    robustness_checks: dict
    interpretation_boundary: str
    verify_status: str
```

---

# 十七、ResearchState 修改要求

当前 `ResearchState` 使用大量裸 `Dict`：

```python
output_tutor: Dict
output_evidence: Dict
output_design: Dict
output_stat: Dict
output_writer: Dict
output_reviewer: Dict
```

需要改为明确 TypedDict 或 Pydantic 类型。

建议：

```python
class ResearchState(TypedDict):
    project_meta: ProjectMetaDict

    current_stage: str
    task_status: str
    stage_history: list[dict]

    task_ledger: TaskLedger
    progress_ledger: ProgressLedger
    evidence_ledger: list[EvidenceItem]

    artifact_refs: list[ArtifactRef]
    data_asset_refs: list[DataAssetRef]
    execution_run_refs: list[ExecutionRunRef]

    output_tutor: TutorOutput
    output_evidence: EvidenceOutput
    output_design: DesignOutput
    output_stat: StatisticalOutput
    output_writer: WriterOutput
    output_reviewer: ReviewerOutput

    recent_rounds: list[dict]
    short_memory_summary: ShortMemorySummary | None
    long_memory_refs: list[str]

    risk_flags: list[RiskEvent]
    approval_requests: list[ApprovalRequest]
    quality_metrics: dict
    error_log: list[ErrorEvent]
```

注意：

- 大文件只保存 URI 和哈希；
- 不把完整 PDF、代码、SPSS 输出、图像放入 State；
- State 只承担运行上下文和索引。

---

# 十八、Agent 权限修正

当前底座文档存在一个矛盾：

- 一方面规定 Agent 只能写自己的 `output_xxx`；
- 另一方面又允许 Agent 修改 `human_approval_needed`、`risk_flags`、`error_log` 和部分证据字段。

需要改成：

> Agent 不直接修改全局字段，只返回结构化 `AgentResult`，由 Controller 校验后合并。

```python
class AgentResult(TypedDict):
    output: dict
    evidence_candidates: list[EvidenceItem]
    artifact_candidates: list[ArtifactRef]
    risk_events: list[RiskEvent]
    approval_request: ApprovalRequest | None
    requested_transition: str | None
```

流程：

```text
Agent 返回 AgentResult
→ Controller 校验权限
→ Controller 更新 EvidenceLedger / ArtifactStore / RiskFlags
→ Controller 决定状态流转
```

---

# 十九、LangGraph Reducer 要求

当前状态包含很多列表：

- `stage_history`
- `evidence_ledger`
- `risk_flags`
- `error_log`
- `artifact_refs`
- `execution_runs`

多个 Worker 并行写同一字段时必须定义 Reducer。

示例：

```python
from typing import Annotated

class ResearchState(TypedDict):
    stage_history: Annotated[list[dict], merge_stage_history]
    evidence_ledger: Annotated[list[EvidenceItem], merge_evidence_by_id]
    risk_flags: Annotated[list[RiskEvent], merge_risk_events]
    error_log: Annotated[list[ErrorEvent], merge_error_events]
    artifact_refs: Annotated[list[ArtifactRef], merge_artifacts_by_id]
```

不能让并行 Worker 直接返回完整 `ResearchState`。

节点应该返回局部更新。

---

# 二十、人工审批设计

当前人工审批不能只写成一个简单节点。

需要定义：

```python
class ApprovalRequest(TypedDict):
    approval_id: str
    project_id: str
    stage: str
    artifact_ids: list[str]
    question: str
    allowed_actions: list[str]
    requested_at: str
    resolved_at: str | None
    decision: str | None
    decided_by: str | None
```

人工审批节点需要：

- `thread_id`；
- durable checkpointer；
- LangGraph interrupt；
- resume；
- 幂等键；
- 审批日志；
- 恢复后防止副作用重复执行。

必须人工确认的事项：

- 最终研究问题；
- 纳入排除标准；
- 伦理和隐私方案；
- 研究设计；
- 统计分析计划；
- 数据异常和缺失值处理决策；
- 关键结果解释；
- 最终论文发布。

---

# 二十一、长期记忆与存储分类

当前文档只允许证据综述 Agent 写长期记忆，范围过窄。

应拆分为：

## 21.1 SourceEvidenceStore

保存：

- 公开论文；
- 量表；
- 理论；
- 原文证据；
- PaperCard；
- EvidenceMatrix。

## 21.2 DecisionStore

保存：

- 人工批准的研究问题；
- 研究设计；
- 统计分析计划；
- 结果解释决策；
- 发布决策。

## 21.3 ArtifactStore

保存：

- 代码；
- 表格；
- 图形；
- SPSS 输出；
- 论文；
- PPT；
- 审稿报告。

## 21.4 ExecutionStore

保存：

- 数据版本；
- 环境；
- 软件版本；
- 参数；
- 随机种子；
- 日志；
- 错误记录；
- 输出索引。

---

# 二十二、Chroma 嵌入方案必须修正

当前原方案中：

- 中文使用 `bge-large-zh-v1.5`，1024 维；
- 英文使用 `text-embedding-3-small`，1536 维；
- 两套向量放在同一个 Chroma Collection。

这个设计不能直接使用。

不同维度的向量不能放入同一个 Collection。

建议二选一。

## 22.1 MVP 推荐方案：统一多语言嵌入模型

中英文统一使用一个模型和相同维度。

优点：

- 结构简单；
- 检索统一；
- 适合比赛第一版；
- 减少向量融合复杂度。

## 22.2 完整方案：双 Collection

```text
public_kb_bge_1024
public_kb_openai_1536

private_kb_bge_{project_id}
private_kb_openai_{project_id}
```

查询时：

```text
中文 Collection 检索
+
英文 Collection 检索
→ 分数归一化
→ RRF 融合
→ MMR 重排序
```

---

# 二十三、完整主状态机

建议保留主状态机：

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
FAILED
BLOCKED
WAITING_HUMAN
```

数据分析阶段内部使用 Subgraph。

---

# 二十四、停滞和返工规则

触发条件：

- 相同工具和参数重复执行两次；
- 连续三步没有新证据或有效工件；
- 连续两次修改后质量指标没有提高；
- 关键 Agent 结论持续冲突；
- 缺少数据、论文全文或伦理信息；
- 超过时间、调用次数或费用预算；
- Reviewer 连续两次指出同一错误；
- SPSS 与 Python 关键结果不一致；
- Codex 代码连续运行失败；
- 数据哈希与批准版本不一致。

处理规则：

1. 第一次失败：原执行模块定向修复；
2. 第二次失败：控制器重新拆解任务或更换执行方式；
3. 第三次失败：停止自动执行并请求人工处理；
4. 缺少真实证据或数据：直接 `BLOCKED`；
5. 严禁生成模拟结果冒充真实结果。

---

# 二十五、数据和科研诚信约束

系统必须执行：

- 不使用未经脱敏的真实个人数据；
- 不伪造实验数据；
- 不伪造文献；
- 不自动将模型输出标记为人工核验；
- AI 生成内容需要明确标识；
- 所有正式统计结果必须来自真实执行；
- 所有关键数字必须可定位到运行结果；
- 所有文献主张必须能回到原始来源；
- 所有发布版本必须经过人工确认。

来源状态建议：

```text
demo_seed
model_generated_unverified
source_verified
human_verified
```

只有：

```text
source_verified
human_verified
```

可以用于正式结论。

---

# 二十六、比赛 Demo 建议流程

三分钟演示建议：

## 1. 输入研究想法

```text
我想研究生成式 AI 对师范生 STEM 项目式学习的影响。
```

系统生成：

- ResearchContract；
- 研究问题树；
- 待确认事项。

## 2. 展示文献链路

- 检索式；
- 数据库；
- PRISMA；
- PaperCard；
- 原文定位；
- 冲突证据；
- 研究空白。

## 3. 展示研究设计

- 准实验设计；
- 变量图；
- 量表建议；
- 分析计划；
- 伦理检查；
- 用户点击批准。

## 4. 上传数据

例如：

```text
STEM_AI_quasi_experiment.xlsx
```

系统执行：

- 隐私字段识别；
- 数据审计；
- 缺失值检查；
- 数据冻结；
- 哈希记录。

## 5. Codex 生成代码

展示：

- Python 清洗代码；
- SPSS Syntax；
- Python 复核代码；
- 图表代码；
- 测试代码。

## 6. SPSS 与 Python 双轨分析

展示：

- SPSS 正式结果；
- Python 复核；
- 一致性报告；
- 结果写入证据账本。

## 7. 论文写作和审稿

展示：

- 主张—证据映射；
- 论文段落；
- Reviewer 指出过度因果表述；
- 写作 Agent 修订。

## 8. 最终科研包

展示：

- 论文；
- 证据矩阵；
- PRISMA；
- 研究方案；
- 代码；
- SPSS 输出；
- 日志；
- 图表；
- 审稿报告；
- 可复现包。

---

# 二十七、效果验证方案

## 27.1 文献能力

指标：

- 目标论文召回率；
- 纳入排除准确率；
- 原文定位率；
- 结构化字段准确率；
- 引用支持主张比例；
- PRISMA 完整率。

## 27.2 研究设计能力

指标：

- 研究问题与设计匹配度；
- 变量定义完整率；
- 混淆变量覆盖率；
- 伦理风险识别率；
- 专家修改次数。

## 27.3 数据分析能力

指标：

- 数据问题检出率；
- 代码运行成功率；
- SPSS 与 Python 结果一致率；
- 统计结果复现率；
- 图表和正文数字一致率；
- 计划外分析标记完整率。

## 27.4 写作与用户指标

指标：

- 主张—证据覆盖率；
- 无依据表述数量；
- 用户任务完成时间；
- 人工返工次数；
- 用户满意度；
- 方法专家评分。

## 27.5 架构对照实验

建议比较：

1. 单 Agent；
2. 固定六 Agent；
3. 动态多 Agent；
4. 动态多 Agent但无证据核验；
5. 动态多 Agent但无人工闸门。

比较：

- 准确率；
- 成本；
- 时间；
- 错误传播；
- 返工次数；
- 用户满意度。

---

# 二十八、开发优先级

## 第一优先级：跑通最小状态机

先完成：

- `core` 数据结构；
- LangGraph 主状态机；
- Controller；
- AgentResult；
- 人工审批；
- REWORK / BLOCKED / FAILED；
- Checkpoint；
- 最小端到端流程。

## 第二优先级：真实文献链路

完成：

- PDF 解析；
- 文献切片；
- 向量库；
- 混合检索；
- PaperCard；
- 原文定位；
- EvidenceMatrix；
- PRISMA。

## 第三优先级：科研工件与存储

完成：

- ArtifactRef；
- ArtifactStore；
- 版本；
- 哈希；
- Provenance；
- DecisionStore；
- ExecutionStore。

## 第四优先级：数据分析 MVP

完成：

- CSV/Excel 导入；
- 数据审计；
- 数据冻结；
- AnalysisPlan；
- Python 统计执行；
- 结果卡片；
- 运行日志；
- 一键复现。

## 第五优先级：Codex 接入

完成：

- CodingProvider；
- CodexProvider；
- CodeSpecification；
- 代码版本；
- 沙箱；
- 测试；
- 自动修复循环。

## 第六优先级：SPSS 接入

完成：

- SPSS 安装检测；
- Syntax 执行；
- 输出导出；
- 输出解析；
- Python 复核；
- 结果一致性报告。

## 第七优先级：论文写作与审稿

完成：

- ClaimEvidenceMap；
- 论文生成；
- 引用核验；
- 数字一致性；
- 独立审稿；
- 自动修订。

## 第八优先级：前端与比赛展示

完成：

- 项目工作台；
- 状态可视化；
- Agent 运行轨迹；
- 原文侧边栏；
- PRISMA 图；
- 图表；
- Demo 视频。

---

# 二十九、第一版 MVP 边界

第一版建议支持：

- STEM 教育；
- 系统综述；
- 准实验；
- 混合研究；
- PDF；
- CSV；
- Excel；
- `.sav` 可后续支持；
- 描述统计；
- 信度分析；
- t 检验；
- ANOVA；
- ANCOVA；
- 回归；
- 基础效应量；
- APA 风格；
- IMRaD 论文结构。

第一版暂不支持：

- 所有教育学分支；
- 所有统计模型；
- 自动投稿；
- 自动替代研究者审批；
- 未脱敏真实学生数据；
- 自动生成实验数据；
- 完全无人监督生成论文；
- 依赖个人桌面 Codex 客户端；
- 依赖 SPSS 界面自动点击。

---

# 三十、当前最重要的开发结论

1. 当前两份底层文件可以保留；
2. 它们只能作为 GraphRAG、Memory 和流程控制底座；
3. 需要新增科研工件、数据、编码、统计和执行层；
4. Codex 不新增为独立科研 Agent，而是作为 CodingProvider；
5. SPSS 不作为 Agent，而是确定性统计执行工具；
6. 数据分析阶段使用 LangGraph Subgraph；
7. SPSS 结果必须由 Python 独立复核；
8. ResearchState 只存引用，不存大文件；
9. 所有 Agent 通过 AgentResult 返回请求，由 Controller 合并；
10. 不同维度嵌入不能放在同一个 Chroma Collection；
11. 并行 Worker 写列表字段必须定义 Reducer；
12. 人工审批必须使用可恢复、可审计、幂等的流程；
13. 所有正式结果必须可追溯至证据、数据、代码和运行记录；
14. 项目最终定位不是“AI 自动写 SCI”，而是“可追溯科研协作系统”。

---

# 三十一、Codex 当前建议任务

Codex 在读取本文档后，优先执行以下任务：

## Task 1：审查并重构目录结构

- 根据第十一章生成新的 `src/` 目录；
- 保留现有模块；
- 新增 `artifacts`、`research_data`、`coding`、`statistics`、`executors`；
- 暂时只创建骨架和类型，不实现全部业务。

## Task 2：重构核心类型

重点实现：

- `ArtifactRef`
- `DataAsset`
- `AnalysisPlan`
- `CodeArtifact`
- `ExecutionRun`
- `StatisticalResultCard`
- `ApprovalRequest`
- `AgentResult`
- `RiskEvent`
- `ErrorEvent`

## Task 3：重构 ResearchState

要求：

- 去除裸 `Dict`；
- 使用 TypedDict 或 Pydantic；
- 大文件使用引用；
- 列表字段定义 Reducer；
- 支持 LangGraph checkpoint。

## Task 4：实现最小状态机

先跑通：

```text
INTAKE
→ SCOPED
→ STUDY_PROTOCOL_APPROVED
→ DATA_READY
→ ANALYZED
→ DRAFTED
→ VERIFIED
→ RELEASED
```

暂时使用 Mock Agent。

## Task 5：实现数据分析 MVP

先不接 SPSS，优先实现：

- CSV/Excel 导入；
- 数据审计；
- 数据冻结；
- Python 描述统计；
- t 检验；
- ANCOVA；
- RunManifest；
- StatisticalResultCard；
- 一键复现。

## Task 6：为 Codex/SPSS 保留适配器接口

创建但可暂不实现：

- `CodingProvider`
- `CodexProvider`
- `SPSSAdapter`
- `PythonAdapter`
- `ConsistencyChecker`

## Task 7：编写测试

至少覆盖：

- 状态流转；
- Agent 权限；
- Artifact 版本；
- 数据哈希；
- 数据冻结；
- Reducer 去重；
- 审批恢复；
- 运行记录；
- 结果卡片；
- BLOCKED / REWORK。

---

# 三十二、编码要求

- Python 3.11+；
- 类型完整；
- 使用 Pydantic v2 做运行时校验；
- LangGraph 节点返回局部更新；
- 所有外部工具使用 Adapter；
- 所有大文件使用 ArtifactRef；
- 所有数据和代码有 SHA256；
- 所有执行有 RunManifest；
- 所有错误结构化记录；
- 所有权限由 Controller 校验；
- 所有接口传递 `user_id / project_id / run_id`；
- 禁止 Agent 直连 Chroma、Neo4j、PostgreSQL；
- 禁止 Agent 直接修改流程阶段；
- 禁止统计模块修改冻结数据；
- 禁止代码执行覆盖原文件；
- 禁止生成虚假统计结果；
- 代码需有单元测试和错误处理；
- 目录、类型和接口文档同步更新。

---

# 三十三、最终产品描述

> STEM-SCI 是一个面向 STEM 教育研究的可追溯科研协作系统。系统使用确定性流程控制器协调导师规划、证据综述、研究设计、科研计算与数据分析、论文写作和独立审稿六类 Agent，并通过 GraphRAG、分层记忆、科研工件、Codex 代码能力、SPSS 统计执行和 Python 独立复核，形成从研究需求到论文与复现包的完整闭环。所有关键结论可以回到原始文献、真实数据、分析代码和运行记录，关键科研决策由研究者确认。
