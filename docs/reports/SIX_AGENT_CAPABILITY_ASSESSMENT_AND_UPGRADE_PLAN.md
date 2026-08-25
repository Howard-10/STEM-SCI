# STEM-SCI 六类 Agent 能力评估与高级化优化方案

**评估日期：** 2026-08-11
**评估对象：** 当前本地分支 `feature/context-knowledge-mvp`
**定位：** 后端 Phase 1/早期 MVP 审计，不包含未合入的远程旧架构代码。

## 1. 总体结论

STEM-SCI 目前的六类专业 Agent 在**角色划分、权限边界和基础工件契约**上已经齐全，不需要增加第七个 Agent。系统已形成“Agent 负责推理和候选工件、Controller 负责阶段和审批、Operator 负责确定性执行”的正确方向。

但六个角色的实现深度并不一致：当前系统已跑通一条窄范围的 `CSV → Python → StatisticalResultCard → 数字审稿` 链路；导师规划、研究设计和数据分析现已能产生结构化候选工件；证据综述和论文写作已有结构化 GPT 流水线，但还未在真实模型和真实知识库上验收。

因此，当前可定位为：

```text
可追溯科研智能体系统的后端 MVP
不是已完成的通用高级科研智能体
```

### 本轮已落地的增强

1. 导师规划 Agent 已从空引用升级为 `PlanningBrief → 8 个结构化候选工件`；输出范围、问题树、可行性前提、证据需求、风险和人工决策点；可选模型只补充受 JSON Schema 限制的候选理由和未决问题。
2. 研究设计 Agent 已从空引用升级为 `ResearchDesignBrief → 15 个结构化候选工件`；默认随机平行组重复测量设计，不将交叉实验伪装为默认方案；可选模型只补充 Estimand、测量和预注册风险理由，不改变确定性协议候选。
3. 数据分析 Agent 的 PRE_ANALYSIS 与 POST_EXECUTION 输出现在均包含真实候选工件正文；预注册计划必须是已人工批准并冻结的版本。
4. 证据综述与论文写作在未配置模型时也有保守的确定性降级：前者会整理已有 Evidence 为筛选账本、PaperCard 和仅 `MENTIONING` 的证据矩阵；后者只产生不含结果数字、方向或文献结论的中英论文骨架。两者均明确标记 `INCOMPLETE`，不能被当作正式综合或论文。
5. 证据与写作模块新增正式用途保护：`demo_seed` 不能支撑正式证据综合或正式论文主张；不合规的证据矩阵、PaperCard 或 ClaimGraph 会被降级为不完整候选。
6. 独立审稿 Agent 可以将只读 Finding / RevisionRequest / ReviewReport 标准化为候选工件，并拒绝跨项目结果卡；还可从 ClaimGraph、证据、协议和结果卡自动发现基础追溯断裂。
7. `AgentResult` 现在会序列化候选工件正文而非只暴露 `candidate://...` 引用；六类 Agent 的独立输出均已通过同一候选工件合并校验，可由未来 LangGraph 读取、校验和持久化。
8. 导师规划、研究设计、数据分析（含结果解释）已提供以 `AgentInput` 为入口的授权适配方法：未获 Controller 授权的候选类型会被剔除并显式标记 `OUTPUT_CAPABILITY_NOT_GRANTED`，不会悄悄流向下游。
9. 可选模型 Provider 不可用、网络失败或结构化输出失败时，规划、设计、证据综述和论文写作均会返回保守的确定性候选与 `MODEL_GENERATION_FAILED` 风险标记，而不是抛出未经处理的异常中断编排。

本轮没有把这些 Agent 接入 LangGraph、没有增加新 Agent、没有修改 Controller 的阶段权力，也没有让任何 Agent 执行数据或编造统计数字。

## 2. 评估标准

一个 Agent 达到“高级科研 Agent”水平，至少应同时满足：

1. 能基于真实项目输入形成实质性、结构化的科研工件，而不仅是空引用；
2. 能明确引用其允许使用的证据、协议、数据版本或结果卡；
3. 不越权修改数据、统计数字、审批结果或项目阶段；
4. 能被 Controller 稳定调度，并将输出传给下游 Agent/Operator；
5. 有自动测试、失败路由、审计记录和人工审批边界；
6. 在固定案例与真实材料上有质量评估证据。

## 3. 六类 Agent 当前能力

| Agent | 当前已具备能力 | 当前不足 | 当前成熟度 |
| --- | --- | --- | --- |
| 导师规划 Agent | 以 `PlanningBrief` 生成 ResearchContract、可行性报告、研究问题树、范围、证据需求、风险、路线图和未决问题等 8 个结构化候选工件；由 Controller 在范围审批处暂停。 | 候选内容目前是受输入约束的确定性编译，尚未接入可审计 LLM 推理、真实文献可行性评估或样本量估算。 | 基础可用 |
| 证据综述 Agent | 可接收 ContextBundle；具备筛选、PaperCard、证据矩阵、冲突/研究空白、限定语料综合的结构化流水线；校验引用、项目范围和正式用途的核验状态。 | 未配置真实 GPT 时退化为候选引用；当前检索为 SQLite 关键词检索，不是 GraphRAG；尚未以真实物理 STEM 文献库完成质量验收。 | 部分可用 |
| 研究设计 Agent | 以 `ResearchDesignBrief` 编译研究问题、Estimand、DAG、协议、抽样、干预、测量、数据字典、预注册分析计划草案和质量闸门计划等 15 个结构化候选工件；明确在数据采集前需要人工批准。 | 目前是受输入约束的候选协议编译，未完成样本量计算、伦理文本审查、任务等值性分析或真实因果 DAG 验证。 | 基础可用 |
| 科研计算与数据分析 Agent | 输出并实际附带数据审计规格、处理方案、可执行分析计划候选、代码规格、模型诊断、稳健性检查、风险与解释边界；必须以已冻结的预注册计划为前提，明确禁止改数据、执行代码或生成统计数字。 | 真实审批与冻结状态仍有部分依赖 Controller 调用方提供的引用；模型执行范围很窄，当前实际 MVP 为 CSV + Python-only 简单组间分析。 | 可用但范围窄 |
| 论文写作 Agent | 具备 AtomicClaimGraph、论文大纲、中英文草稿、双语一致性、写作充分性检查；RESULT Claim 必须关联结果卡；正式用途下文学/解释主张只能使用 `source_verified` 或 `human_verified` 证据，解释主张还必须关联 RESULT、解释边界和人工确认。 | 未配置真实 GPT 时不生成正式正文；尚未在真实文献、真实 ResultCard、真实协议的组合上验收。 | 部分可用 |
| 独立审稿 Agent | 已实现引用、方法、教育学、可复现性四类审查契约；论文数字与 StatisticalResultCard 的核验已接入 Controller，可 PASS 或定向 REWORK；拒绝把其他项目的结果卡带入数值审稿。 | 引文/方法/教育学审稿尚需外部人工构造输入，尚未自动从论文草稿、ClaimGraph、协议和证据矩阵中抽取材料。 | 部分可用 |

## 4. 当前已验证的能力

截至本次评估，以下工程检查均通过：

```text
后端测试：147 passed
Ruff：通过
Mypy：通过（101 个源码文件）
前端 TypeScript 检查：通过
前端生产构建：通过
```

已实际验证的关键闭环：

```text
已批准的研究协议
→ 数据分析 Agent 生成 Pre-analysis Specification
→ RawDataset 数据审计
→ 人工批准处理
→ ProcessedDataset
→ 人工批准冻结
→ FrozenDataset + SHA256
→ SchemaCompatibilityGate
→ 人工批准执行
→ Python ExecutionRun
→ SINGLE_ENGINE ResultValidationReport
→ StatisticalResultCard
→ 独立可复现性审稿
→ PASS 后仍等待人工确认；数字不一致则定向 REWORK 至论文写作
```

该闭环只能证明当前 Python-only 演示路径可用；不能证明 SPSS 双轨验证、任意统计模型、GraphRAG 或完整论文发布已完成。

## 5. 当前最关键的系统缺口

### 5.1 通用 Agent 路由与正式数据链尚未完全统一

当前存在通用六 Agent 路由和正式数据流水线两条路径。正式数据流水线正确地要求冻结、执行和验证；但通用流程中的数据分析候选审批可能在没有真实数据执行时进入 `ANALYZED`。

必须统一为唯一正式链路：

```text
ResearchQuestion / StudyProtocol 批准
→ PreregisteredAnalysisPlan 人工批准并冻结
→ 数据采集
→ RawDataset
→ ProcessedDataset
→ FrozenDataset
→ ExecutableAnalysisPlan
→ CodeSpecification
→ CodeArtifact
→ ExecutionRun
→ ResultValidationReport
→ StatisticalResultCard
→ AtomicClaim
→ Review
→ Release
```

### 5.2 Codex、代码审查与沙箱尚未落地

目前存在 `CodeSpecification` 与 `CodeArtifact` 数据模型，也存在 `coding_provider` Operator 名称，但尚未实现：

- CodexCodingProvider；
- ResearchCodeSandbox；
- CodeReviewGate；
- FrozenDataset 只读挂载；
- 代码运行资源、网络、目录、依赖安装和删除权限限制。

### 5.3 SPSS 仅有协议预留

系统已定义 `PYTHON_ONLY`、`SPSS_PYTHON_DUAL`、`SINGLE_ENGINE`、`CROSS_ENGINE` 等模式约束，但没有真实 SPSSAdapter、SPSS Syntax 生成、SPSS 输出解析或跨引擎比较执行。

### 5.4 质量闸门尚不完整

已实际执行：

- DataAuditGate；
- SchemaCompatibilityGate。

仍缺少实际 Gate Engine 与以下闸门实现：

- PaperCardGate；
- EvidenceMatrixGate；
- StudyProtocolGate；
- AnalysisPlanGate；
- CodeReviewGate；
- ResultConsistencyGate；
- ClaimEvidenceGate；
- ReleaseGate。

### 5.5 GraphRAG、长期 Memory 和 LangGraph 尚未接入

当前 Context MVP 已支持 PDF/TXT/Markdown/JSON 上传、SQLite 存储、切片、关键词检索、证据核验和 ContextBundle；但代码明确使用的是本地 SQLite MVP，尚未接入向量检索、GraphRAG、长期 Memory 或 LangGraph StateGraph。

### 5.6 真实模型运行和质量评估不足

证据综述与论文写作可在 Fake Provider 下测试结构化输出，但未配置真实 GPT/Codex Provider 时不会产生正式内容。高级科研 Agent 必须在真实、可核验的物理 STEM 文献语料和固定案例上评估。

截至本次只读审计，默认 `.stem_sci/context.db` 中的 `sources`、`chunks` 与 `evidence` 均为 0；仓库的 `data/local/literature_pdfs/` 已有本地 PDF 资料，但尚未被导入 Context 服务并完成核验。因此不能把当前测试误表述为“真实知识库端到端验收”。资料导入、切片、来源核验和真实模型评测应由负责人另行确认后执行。

## 6. 高级化优化路线

### 阶段 A：先把六个 Agent 做“实”

1. 已完成：导师规划 Agent 的确定性结构化候选输出（ResearchContract、范围、问题树、可行性、未决问题）。
2. 已完成：研究设计 Agent 的确定性结构化候选输出（ResearchQuestion、Estimand、CausalDAG、StudyProtocol、PreregisteredAnalysisPlan 草案）。
3. 下一步：接真实模型 Provider，并在响应后用 Pydantic 模型和确定性规则验证输出；真实模型必须通过固定语料验收才可扩大使用。
4. 下一步：由未来的 LangGraph/Controller 层将候选工件持久化到 ArtifactStore / ArtifactContentStore；Agent 本身只返回候选，不能自行写账本。

**阶段 A 完成标准：** 用户给出一个研究想法后，能得到真实、有内容、可审阅的研究范围、问题树、研究协议和预注册计划候选。

### 阶段 B：做成一条不可跳步的 Controller 主链

1. 移除通用路由中绕过数据流水线进入 `ANALYZED` 的可能。
2. 让每一步只读取上游已批准的真实工件。
3. 在所有失败路径中执行定向返工：第一次原模块修复，第二次重新拆解/更换 Operator，第三次 `WAITING_HUMAN`；数据、伦理、权限不足直接 `BLOCKED`。
4. 使用统一的 `decision_scope` 与 `blocked_target_ids`，支持 RUN / ARTIFACT / TASK / STAGE / PROJECT 粒度。

**阶段 B 完成标准：** 任何人都无法在缺少预注册、冻结数据、执行记录或结果验证时进入论文写作与发布阶段。

### 阶段 C：补齐 Codex 与科研执行安全

1. 将 Codex 实现为 Controller 调用的 CodingProvider，不列为第七个科研 Agent。
2. 固化流程：`ExecutableAnalysisPlan → CodeSpecification → CodeArtifact → CodeReviewGate → ExecutionRun`。
3. 建立 ResearchCodeSandbox：FrozenDataset 只读、仅允许写入当前 Run 目录、禁止网络/宿主目录/任意子进程/依赖安装/危险删除。
4. 分离 LearnerCodeSandbox 与 ResearchCodeSandbox。

**阶段 C 完成标准：** 同一 FrozenDataset 与同一代码版本可重复得到可追溯 ExecutionRun，且越权代码只阻塞对应 Run。

### 阶段 D：补齐模型、审稿与科研可信度

1. 主 Demo 接入可替换的 AnalysisModelSpecification；实现随机平行组重复测量模型或线性混合效应模型，不把框架写死为 LMM。
2. SPSS 可用时实现 `SPSS_PYTHON_DUAL → CROSS_ENGINE → cross_engine_verified`；不可用时明确标记 `PYTHON_ONLY → SINGLE_ENGINE → execution_verified`。
3. 自动从 AtomicClaimGraph、ManuscriptDraft、EvidenceMatrix、StudyProtocol、ResultCard 构建 Reviewer 输入。
4. 对 Citation / Method / Pedagogy / Reproducibility Reviewer 进行仲裁，并让 Controller 精确路由返工。

**阶段 D 完成标准：** 论文中的每个数字、方法和证据主张均能反向追溯；错误数字、无证据引用、协议不一致均能自动发现。

### 阶段 E：最后再增强知识能力和界面

1. 在 Context MVP 稳定后引入向量检索、GraphRAG 和分层 Memory；不同嵌入维度必须使用不同 Collection。
2. 至少构建三个固定评测案例；比较单 Agent、固定多 Agent、动态多 Agent。
3. 进行至少两位目标用户测试，形成效果验证报告和三分钟演示脚本。
4. 最后才做前端工作台，用于展示真实已经跑通的工件、审批、执行和返工。

## 7. 推荐开发顺序

```text
1. 固定六 Agent 的真实输入样例、输出 JSON Schema 和单元测试（本轮已完成第一版）
2. 真实 GPT 驱动的证据综述和论文写作固定语料验收
3. Reviewer 自动从 ClaimGraph、草稿、结果卡和证据矩阵取材
4. 主 Demo 的重复测量 / LMM 与 SPSS 双轨
5. 由你使用 LangGraph 将已成熟的六 Agent 候选工件接入正式工件主链
6. CodexCodingProvider + CodeReviewGate + ResearchCodeSandbox
7. GraphRAG、Memory、评测和前端
```

## 8. 最终判断

当前系统已经具备高级科研 Agent 系统最重要的**治理理念**：证据受限、数据冻结、执行可追溯、结果不可由模型编造、审稿独立、人工保留发布权。

要真正达到高级科研 Agent 水平，下一步不应扩大 Agent 数量或抢先制作页面，而应让现有六个 Agent 产生真实工件，并由唯一的 Controller 将这些工件、确定性执行器和人工审批连接成一条不可跳步、可复现、可返工的正式科研链路。
