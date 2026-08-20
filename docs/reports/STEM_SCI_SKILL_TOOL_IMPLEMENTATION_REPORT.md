# STEM-SCI Skill 与 Tool 增量建设报告

**报告日期**：2026-08-20  
**代码分支**：`feature/literature-writing-agents`  
**远程仓库**：`https://github.com/Howard-10/STEM-SCI.git`

## 1. 建设结论

本阶段在六智能体 Controller 工作流之上增加了版本化 Skill/Tool 治理层：

- Skill 负责描述某个 Agent 在某类任务中的能力组合、输入输出契约和风险级别。
- Tool 负责执行一个确定的本地操作，必须经过 Controller Tool Gateway 的授权、项目隔离、审批、幂等和审计。
- Agent 只提出结构化 `ToolRequest`，不能直接修改流程状态、审批状态或正式研究结论。
- ToolRun 只保留可审计的引用和状态，不保存 Prompt、API Key、原始模型响应或沙箱原始输出。

当前共配置 **15 个 Skill**，Tool 注册表共包含 **59 个版本化 Tool**。其中 Context/Evidence、研究设计、数据分析、论文写作和独立审查均已有本地执行适配器；研究设计、数据分析、写作和审查中的部分实现目前是确定性候选输出适配器，不等同于完整的生产级科研引擎。

## 2. 六个 Agent 的 Skill 增量

| Agent | 新增 Skill | Skill 任务范围 | 主要绑定 Tool |
|---|---|---|---|
| `mentor_planning` 导师/规划 Agent | `research_scope_planning@v1`、`research_feasibility_assessment@v1` | 研究范围、路线规划、可行性评估 | `context_bundle_read@v1`、`research_scope_validator@v1`、`feasibility_checker@v1` |
| `evidence_review` 证据综述 Agent | `bounded_corpus_review@v1`、`source_screening@v1`、`citation_grounding@v1` | 有限语料综述、来源筛选、引用溯源 | `context_bundle_read@v1`、`knowledge_base_search@v1`、`source_verification_checker@v1`、`evidence_ref_validate@v1`、`bounded_synthesis_validator@v1` |
| `research_design` 研究设计 Agent | `research_question_formulation@v1`、`protocol_draft_validation@v1` | 研究问题、估计目标、研究方案和预注册草案 | `research_question_validator@v1`、`protocol_schema_validator@v1` |
| `data_analysis` 数据分析 Agent | `data_readiness_audit@v1`、`statistical_analysis_execution@v1`、`result_card_generation@v1` | 数据准备、受限分析执行、结果卡和结果解释边界 | `dataset_schema_profile@v1`、`data_quality_audit@v1`、`python_analysis_sandbox@v1`、`result_validation_checker@v1`、`statistical_result_card_builder@v1` |
| `paper_writing` 论文写作 Agent | `atomic_claim_graph_construction@v1`、`bilingual_manuscript_rendering@v1` | 原子化主张、证据映射、中英文稿件生成 | `atomic_claim_validator@v1`、`claim_evidence_mapper@v1`、`manuscript_renderer_zh@v1`、`manuscript_renderer_en@v1`、`bilingual_consistency_checker@v1` |
| `independent_review` 独立审查 Agent | `citation_review@v1`、`methodology_review@v1`、`reproducibility_review@v1` | 引用、方法、统计、复现和双语稿件审查 | `citation_audit@v1`、`evidence_reference_audit@v1`、`method_protocol_alignment_checker@v1`、`statistical_claim_audit@v1`、`reproducibility_artifact_audit@v1`、`bilingual_draft_audit@v1` |

Skill 清单位置：`backend/src/stem_sci/skills/builtin.py`。Skill 的数据结构、注册和解析分别位于：

- `backend/src/stem_sci/skills/models.py`
- `backend/src/stem_sci/skills/registry.py`
- `backend/src/stem_sci/skills/resolver.py`

## 3. Tool 分类清单

### 3.1 Context、Artifact 与 Evidence Tool

这些 Tool 已接入项目级 ContextService/ArtifactStore，默认禁用网络访问：

- `context_bundle_read@v1`：读取项目 ContextBundle。
- `artifact_resolve@v1`：解析项目级候选 Artifact 内容。
- `artifact_integrity_check@v1`：检查候选内容完整性和哈希。
- `evidence_ref_validate@v1`：校验证据引用是否属于当前项目。
- `knowledge_base_search@v1`：仅搜索项目已导入的本地知识库。
- `source_chunk_reader@v1`：读取项目来源的 SourceChunk。
- `source_verification_checker@v1`：检查证据来源验证状态。
- `citation_deduplicator@v1`：去除重复证据引用。
- `bounded_synthesis_validator@v1`：验证综述是否仅基于已验证、项目内证据和声明的语料边界。

### 3.2 证据加工 Tool

- `paper_screening_executor@v1`：在本地导入语料中生成筛选台账。
- `paper_card_extractor@v1`：从 SourceChunk 生成 PaperCard 候选。
- `evidence_matrix_builder@v1`：从 PaperCard 生成证据矩阵候选。
- `evidence_conflict_detector@v1`：检测支持与对立证据关系。
- `corpus_coverage_calculator@v1`：计算有限语料覆盖情况。

### 3.3 研究设计 Tool

- `research_scope_validator@v1`
- `feasibility_checker@v1`
- `research_question_validator@v1`
- `hypothesis_structure_checker@v1`
- `estimand_validator@v1`
- `causal_dag_checker@v1`
- `sampling_plan_checker@v1`
- `measurement_plan_checker@v1`
- `protocol_schema_validator@v1`
- `preregistration_consistency_checker@v1`
- `intervention_protocol_linter@v1`
- `quality_gate_plan_builder@v1`

这些 Tool 当前主要输出候选验证报告，不直接批准研究方案或推进流程阶段。

### 3.4 数据分析 Tool

- `dataset_catalog_read@v1`
- `dataset_schema_profile@v1`
- `data_quality_audit@v1`
- `missingness_and_outlier_report@v1`
- `data_processing_executor@v1`
- `model_diagnostic_runner@v1`
- `statistical_result_card_builder@v1`
- `result_validation_checker@v1`
- `data_freeze_request_builder@v1`
- `python_analysis_sandbox@v1`

其中 `python_analysis_sandbox@v1` 是高风险 Tool：使用受限 Python 子进程、禁用网络和 native 绕过模块，并限制项目文件范围。分析结果只能形成候选执行结果，不能直接成为正式统计结论或冻结数据集。

### 3.5 论文写作 Tool

- `writing_context_resolver@v1`
- `atomic_claim_validator@v1`
- `claim_evidence_mapper@v1`
- `manuscript_outline_validator@v1`
- `manuscript_renderer_zh@v1`
- `manuscript_renderer_en@v1`
- `bilingual_consistency_checker@v1`
- `citation_consistency_checker@v1`
- `numeric_literal_checker@v1`
- `result_strength_checker@v1`
- `limitation_coverage_checker@v1`
- `reproducibility_statement_builder@v1`
- `table_figure_narrative_builder@v1`

这些 Tool 生成论文结构、主张、证据映射和双语稿件候选；最终稿件仍必须经过 Controller 审批和独立审查。

### 3.6 独立审查 Tool

- `citation_audit@v1`
- `evidence_reference_audit@v1`
- `method_protocol_alignment_checker@v1`
- `statistical_claim_audit@v1`
- `result_limitation_audit@v1`
- `reproducibility_artifact_audit@v1`
- `bilingual_draft_audit@v1`
- `review_finding_builder@v1`
- `revision_request_builder@v1`
- `review_summary_builder@v1`

独立审查 Tool 只能生成 Finding、RevisionRequest 和 ReviewReport 候选，不能直接修改被审查工件，也不能绕过人工审批。

## 4. Tool Gateway 与审计能力

Tool 执行统一经过 `backend/src/stem_sci/tools/gateway.py`：

1. 解析 `tool_id@version` 并检查注册表。
2. 检查 Agent、Task 对应 Skill 是否授权该 Tool。
3. 检查项目范围、权限、审批、网络策略、预算和幂等键。
4. 调用 `BuiltinToolExecutor` 执行本地 Tool。
5. 对候选输出执行 Schema 引用、哈希、项目范围和版本冲突检查。
6. 写入项目级 `ToolRunRecord`、ArtifactRef 和 ArtifactContent。

新增的前端审计位置：

- `frontend/src/api/workflow.ts`
- `frontend/src/pages/WorkflowWorkspacePage.tsx`
- `frontend/src/styles.css`

工作流页面的“Agent 工具运行记录”可以显示 Agent、Skill、Tool、版本、状态、错误码和输出引用数量。

## 5. 当前实现边界

已具备：

- 六 Agent 到 Skill 到 Tool 的版本化绑定。
- 本地 Tool 的 Gateway 执行和 ToolRun 审计。
- 项目级证据、Artifact 和 Context 隔离。
- 有限语料综述验证和证据引用溯源。
- 受限 Python 分析执行边界。
- 候选 Artifact 的不可覆盖写入语义。
- GPT 证据综述和双语论文写作管线的可选接入。

仍属于后续填充阶段：

- 数据分析 Tool 需要接入真实数据集目录、统计计算和结果卡验证逻辑。
- 论文写作和独立审查的部分 Tool 目前是确定性候选适配器，需要继续接入完整领域规则。
- Python 沙箱目前是受限子进程，不等同于容器级或操作系统级安全隔离。
- 尚未配置生产环境认证、限流、密钥托管和部署级权限系统。

## 6. 验证记录

最近一次完整验证结果：

```text
Backend: 221 passed
Ruff: passed
Mypy: passed
Frontend typecheck: passed
Frontend production build: passed
OpenAPI matches app
```

最近相关提交：

```text
2b53039 fix(storage): prevent candidate overwrite races
a31a7a9 fix(platform): enforce task skills and sandbox boundaries
a0352b3 feat(platform): close tool execution and project isolation gaps
810df47 feat(frontend): show tool execution audit
```

