# 六类 Agent 进度对比：上次拉取基线与当前状态

**日期：** 2026-08-13
**当前分支：** `feature/context-knowledge-mvp`
**比较口径：** “上次拉取基线”指团队此前合入并完成检查的六类 Agent 候选工件实现状态，不等同于一次逐文件的远程提交差异。当前状态同时纳入随后完成的 v1.0 确定性数据、统计执行和审稿主链。

## 一、结论先说

上次拉取后，六个 Agent 已经能按权限输出结构化的**候选科研工件**；但它们仍主要是“研究推理与规格提出者”。

当前最大的升级不是又增加了 Agent，而是把其中最关键的“数据分析候选”接上了真正不能由大模型篡改的确定性统计链：

```text
数据分析 Agent 的候选规格
        ↓（Controller + 人工批准）
FrozenDataset → StructuralDataAudit → ModelEligibility
        ↓
AnalysisDataset → CodeSpecification → CodeReview
        ↓（精确内容绑定的人类批准）
statsmodels ExecutionRun → ResultValidationReport → StatisticalResultCard
        ↓
独立审稿 Agent 的只读复现性审查
```

因此，当前系统不再只是六个 Agent 输出“建议”；至少在合成演示数据、`PYTHON_ONLY` 模式和三类冻结模型范围内，已经能够形成真实、可复现、可审计的统计结果链。

## 二、总体对比

| 维度 | 上次拉取后的状态 | 当前状态 | 判断 |
| --- | --- | --- | --- |
| Agent 输出 | 六类角色均能输出 Pydantic 约束的候选工件 | 保留并加强候选工件与权限过滤 | 已稳定 |
| 研究规划与设计 | 能提出范围、问题、协议、预注册草案 | 仍是候选，必须经 Controller 与人工批准 | 正确边界 |
| 数据分析 | Agent 能提出审计、处理、计划、代码规格草案 | Agent 仍不执行；Controller 现可真正审计、冻结、筛选并运行统计 | 实质升级 |
| 数据版本 | 有 Raw / Processed / Frozen 的基础链 | 新增规范化内容哈希、模型专属 AnalysisDataset、资格清单 | 实质升级 |
| 统计数字 | 禁止 Agent 自行生成，但执行能力有限 | 三个真实 statsmodels 执行器可生成 ResultCard | 实质升级 |
| 审批 | 有人工审批节点与候选/正式的区分 | 审批绑定计划、代码、数据、环境和模板哈希 | 实质升级 |
| 独立审稿 | 可产生 Finding / RevisionRequest / ReviewReport | 可核验 ExecutionRun、代码、数据、结果卡的哈希链 | 实质升级 |
| LangGraph 主编排 | 尚未正式接入 | 仍未正式接入；Controller 服务可被后续图调用 | 待完成 |
| SPSS 双引擎 | 契约和适配层预留 | 仍未运行真实 SPSS；当前只有 `PYTHON_ONLY` | 待环境支持 |
| 正式论文/发布 | 写作与审稿候选能力存在 | 仍未跑通真实论文到发布闭环 | 待完成 |

## 三、逐 Agent 对比

### 1. 导师规划 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| 输入 | `PlanningBrief`、研究主题、对象、干预、对照、候选结果与约束 | 相同 |
| 输出 | 研究契约、可行性报告、问题树、研究范围、路线图、文献要求、初始风险、未决问题 | 相同；仍可按 Controller 授权过滤输出类型 |
| 可选模型辅助 | 生成受 JSON Schema 约束的理由和未决问题；失败时退回确定性候选 | 相同 |
| 当前限制 | 不能检索、核验真实文献，也不能批准研究范围 | 相同 |

**解读：** 该 Agent 已具备清晰的“导师规划”角色，但尚不是能自主判断研究可行性的专家模型。其价值是把自然语言研究想法变成可审批、可传递的候选工件。

### 2. 证据综述 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| 输入 | ContextBundle、Evidence、证据筛选/综合请求 | 相同 |
| 输出 | 检索协议、筛选结论、PaperCard、EvidenceMatrix、研究空白与综合候选 | 相同 |
| 真实性约束 | `demo_seed` 和未核验资料不能支撑正式论文结论 | 相同且保留 |
| 当前限制 | 当前知识库仍是基础检索 MVP，不是 GraphRAG；真实物理 STEM 语料的系统验收尚未完成 | 相同 |

**解读：** 它已是“证据工件整理器”，不是自动编造文献综述的聊天机器人。下一步重点是导入、核验并评估真实语料，而不是再给它增加自由对话能力。

### 3. 研究设计 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| 输入 | `ResearchDesignBrief`，包括人群、干预、对照、测量与设计约束 | 相同 |
| 输出 | 研究问题、假设、Estimand、DAG、研究协议、抽样、干预、任务、量规、测量、数据字典、预注册计划草案 | 相同 |
| 默认设计 | 随机平行组重复测量；不把交叉干预当默认方案 | 相同 |
| v1.0 对接 | 预注册协议的契约已新增主估计量、主对比、结果操作化定义和推断政策字段 | 增强 |
| 当前限制 | 仍不能替代伦理审查、样本量论证或真实因果识别审查 | 相同 |

**解读：** 当前从设计候选到统计执行的接口已经更清楚，但设计 Agent 本身依旧不能“冻结”计划或改写实质性分析决定。

### 4. 科研计算与数据分析 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| PRE_ANALYSIS 输出 | `DataAuditSpecification`、`DataProcessingPlanCandidate`、`ExecutableAnalysisPlanCandidate`、`CodeSpecificationDraft`、诊断/稳健性建议 | 保留 |
| POST_EXECUTION 输出 | 读取结果卡后给出解释边界 | 保留 |
| 是否可改数据/执行统计 | 不可以 | 不可以，边界进一步落地 |
| 实际统计执行 | 旧链路仅证明过简单 Python 组均值演示 | 已有三套 v1.0 statsmodels 执行器：主 LMM、迁移 ANCOVA、提示依赖 LMM |
| 数据资格 | 尚未按不同模型拆开 | 已实现 `StructuralDataAudit` 与模型专属资格：C 缺失不影响主 LMM；提示依赖缺失不影响其他模型 |
| 审批约束 | 执行审批引用存在 | 执行前重新核对计划、代码规格、代码工件、审查、AnalysisDataset、环境、模板的内容哈希 |

**解读：** 这是当前提升最大的部分。但要准确表述：**数据分析 Agent 仍然没有“拿数据自己算结果”的权力**；是 Controller 调用确定性 Python 执行器产生结果。这样才符合科研可信性要求。

### 5. 论文写作 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| 输出 | PaperOutline、AtomicClaimGraph、双语草稿、引用与完整性候选 | 相同 |
| 事实约束 | RESULT Claim 必须链接结果卡；正式文献/解释主张需要已核验来源和人工边界 | 相同 |
| 与统计链关系 | 可读取 StatisticalResultCard，但未形成真实论文全链路 Demo | 可读取当前 v1.0 结果卡，但尚未完成真实论文生成/审稿/发布联调 |
| 当前限制 | 未配置/验收真实模型时只能生成保守、不完整候选 | 相同 |

**解读：** 写作 Agent 目前适合“构建可追溯的论文候选结构”，不能宣传为自动完成正式论文。

### 6. 独立审稿 Agent

| 项目 | 上次拉取基线 | 当前 |
| --- | --- | --- |
| 输出 | `ReviewFinding`、`RevisionRequest`、`ReviewReport` | 相同，仍只读 |
| 审稿类型 | 引文、方法、教育学、可复现性、仲裁 | 相同 |
| 数字核验 | 检查论文数字是否对应 ResultCard | 保留 |
| 新增执行包审查 | 无完整不可变执行包 | 新增 `ReviewPacket`：代码规格、代码工件、代码审查、AnalysisDataset、ExecutionRun、验证报告、结果卡、可复现性清单 |
| 发现问题后的动作 | 输出定向返工建议 | 相同；由 Controller 决定 `REWORK` / `BLOCKED` / `WAITING_HUMAN` |

**解读：** 独立性不是“换一个聊天模型”而已，而是通过只读输入、白名单工件、不能访问行级数据和不能调用写服务来保证。

## 四、当前真正跑通的主 Demo

当前可真实执行的是固定的合成 `demo_seed`，不是学生真实数据：

```text
48 名合成参与者
├─ ai_scaffold：24 人
└─ static_prompt：24 人

每组：AB 序列 12 人 + BA 序列 12 人
每人：A / B 重复建模任务 + C 无辅助迁移任务
```

已实际测试的链路：

```text
FrozenDataset
→ StructuralDataAudit
→ ParticipantEligibilityManifest
→ ModelEligibilityManifest
→ AnalysisDataset
→ CodeSpecification
→ CodeArtifact
→ CodeReviewResult
→ HumanExecutionApproval
→ ExecutionRun
→ ResultValidationReport (SINGLE_ENGINE)
→ StatisticalResultCard (execution_verified)
→ Independent Reviewer ReviewPacket
```

已覆盖的失败案例：

1. C 任务迁移分缺失时，`transfer_ancova` 资格失败，但 `primary_lmm` 仍可使用该参与者；
2. FrozenDataset 或 AnalysisDataset 哈希变化时，统计执行不会启动；
3. 人工审批后的数据、代码、环境或计划发生变化时，执行状态为 `NOT_STARTED`；
4. LMM 未收敛、优化警告、方差边界、秩不足或非有限推断时，不能产生正式 ResultCard；
5. 审稿包内的代码/数据/结果哈希链不一致时，独立审稿给出 STAGE 范围的阻断发现。

## 五、当前不能夸大的地方

以下能力尚未完成，汇报时应如实说明：

- 尚未将全部六个 Agent 接入正式 LangGraph 图；
- 尚未接入 IBM SPSS 的真实执行，因此只能称 `PYTHON_ONLY → SINGLE_ENGINE → execution_verified`，不能称双引擎验证；
- Codex 只能作为受审查的候选代码提供者，不决定方法、不直接产出统计数字，也不是默认执行路径；
- 还没有用真实学生研究数据完成正式分析；
- GraphRAG、长期 Memory、真实语料质量评估和论文发布闭环尚未完成；
- 当前开发沙箱仍是 `development_restricted`，真实敏感数据进入前需要容器级隔离。

## 六、对团队协作的建议

下一轮不应再新增第七个 Agent。建议把工作分成四条可并行但接口明确的线：

1. **Controller / LangGraph 线：** 将批准、返工、`WAITING_HUMAN` 和这条 v1.0 执行服务连接为唯一正式流程；
2. **真实数据与统计线：** 准备脱敏数据字典、审批记录和 CSV 样例；确认提示依赖量表是否对两组可比；
3. **知识库与证据线：** 导入、去重、核验物理 STEM 文献，并用真实语料评估检索与证据矩阵；
4. **论文与审稿线：** 以真实 `StatisticalResultCard` 和 `ClaimEvidenceMap` 做一篇短 Demo 论文的原子主张、数字核验和返工演示。

## 七、当前验收证据

截至本报告更新，后端工程检查结果：

```text
Ruff: 通过
Mypy: 通过（125 个源码文件）
Pytest: 198 passed
Compileall: 通过
stem_sci 导入: 通过
```

这些测试证明的是当前实现的工程契约和合成演示链可运行；不等同于真实教育实验的结论已经成立。
