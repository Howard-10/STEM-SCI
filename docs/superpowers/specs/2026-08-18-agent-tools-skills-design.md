# STEM-SCI Agent Tools and Skills Design

**日期：** 2026-08-18  
**状态：** 设计已确认，待用户审阅后编写实施计划  
**适用分支：** `feature/literature-writing-agents`

## 1. Design Goal

为六个 STEM-SCI Agent 建立可审计的 Skill + Tool 两层能力体系，同时保持现有 Controller-mediated 六智能体拓扑、人工审批边界和项目引用型状态模型不变。

- Skill 定义领域推理流程、Prompt 版本、输入输出约束和所需 Tool 组合。
- Tool 执行具体的数据读取、验证、分析或候选工件生成。
- Agent 只能提出结构化 `ToolRequest`。
- Controller Gateway 统一完成权限、项目隔离、预算、审批、执行和审计。
- 第一版优先实现本地可控 Tool；外部服务只保留 Provider 接口，不立即接入。

## 2. Architecture

```text
Agent
  -> Skill resolver
  -> ToolRequest
  -> Controller Gateway
       -> project/permission/version checks
       -> budget/timeout/approval checks
       -> Tool Executor
            -> local Tool / sandbox Tool / external Provider
  -> ToolResultRef and audit record
```

六个 Agent 仍运行在同一个 Python 后端进程内。Skill 和 Tool 不创建新的 Controller Agent 节点。未来可将 Tool Executor 替换为 HTTP/RPC Gateway，而不改变 Agent-facing Skill 契约。

### 2.1 Skill Manifest

每个 Skill 使用版本化清单：

```text
skill_id
skill_version
agent_ids
supported_task_types
required_tool_ids
input_schema_refs
output_schema_refs
prompt_template_refs
validator_refs
risk_level
```

Skill 不具有独立审批或写入权限。Skill 只能解析上下文、生成推理步骤和提出 ToolRequest。

### 2.2 Tool Spec

每个 Tool 使用版本化 `ToolSpec`：

```text
tool_id
tool_version
capability
execution_mode: READ_ONLY | CANDIDATE_OUTPUT | CONTROLLED_WRITE
input_schema_ref
output_schema_ref
required_permissions
project_scope_required
network_policy
sandbox_profile
timeout_seconds
retry_policy
estimated_cost
idempotency_policy
```

现有 `ToolRequest` 扩展方向：

```text
skill_ref
tool_version
input_artifact_refs
required_output_types
reason
```

## 3. Controller Gateway

每次请求按以下顺序执行：

1. 校验 Agent 是否拥有请求的 Skill。
2. 校验 Skill 是否绑定请求的 Tool 和版本。
3. 校验项目 ID、输入工件版本、哈希和来源归属。
4. 校验 Agent 权限、审批引用和当前阶段。
5. 校验 LLM/Tool 预算、超时、重试和幂等策略。
6. 创建 `ToolRunRecord` 并进入执行状态。
7. 执行只读 Tool、候选 Tool 或受控写入 Tool。
8. 校验输出 Schema、哈希、引用完整性和项目隔离。
9. 将候选正文写入 `ArtifactContentStore`，将引用写入 `ArtifactStore`。
10. 写入 `AgentRunRecord`、`ToolRunRecord` 和风险审计，并返回引用。

Tool 不能直接修改 `ResearchState.current_stage`、审批记录、冻结数据、正式统计结果或发布状态。

## 4. Shared Skills

所有 Agent 可使用以下共享 Skill：

| Skill | Purpose | Required Tools |
|---|---|---|
| `project_context_grounding` | 读取当前项目允许上下文 | `context_bundle_read`, `artifact_resolve` |
| `artifact_provenance` | 校验版本、哈希、项目归属和来源链 | `artifact_integrity_check` |
| `claim_evidence_binding` | 检查事实主张和证据引用 | `evidence_ref_validate` |
| `risk_and_sufficiency` | 计算覆盖、缺口和风险 | `coverage_metrics` |
| `audit_trace` | 记录 Skill、Tool、输入和输出引用 | `audit_event_append` |

## 5. Agent Capability Matrix

### 5.1 Mentor Planning Agent

Skills:

- `research_scope_planning`
- `research_feasibility_assessment`
- `research_question_decomposition`
- `project_roadmap_planning`

Tools:

- `context_bundle_read`
- `research_scope_validator`
- `research_question_tree_builder`
- `feasibility_checker`
- `roadmap_builder`
- `literature_requirement_builder`

所有输出均为研究范围、问题树、可行性和路线图候选，不自动批准研究范围。

### 5.2 Evidence Review Agent

Skills:

- `bounded_corpus_review`
- `source_screening`
- `paper_card_extraction`
- `evidence_matrix_synthesis`
- `conflict_and_gap_analysis`
- `citation_grounding`

Tools:

- `knowledge_base_search`
- `source_chunk_reader`
- `source_verification_checker`
- `paper_screening_executor`
- `paper_card_extractor`
- `evidence_matrix_builder`
- `citation_deduplicator`
- `evidence_conflict_detector`
- `corpus_coverage_calculator`
- `bounded_synthesis_validator`

第一版只检索当前项目已导入和已核验语料，不接在线数据库。任何综合结论都必须回指项目内 `EvidenceRef`。

### 5.3 Research Design Agent

Skills:

- `research_question_formulation`
- `hypothesis_and_estimand_design`
- `causal_design_review`
- `sampling_and_measurement_design`
- `protocol_draft_validation`
- `preregistration_consistency_check`

Tools:

- `research_question_validator`
- `hypothesis_structure_checker`
- `estimand_validator`
- `causal_dag_checker`
- `sampling_plan_checker`
- `measurement_plan_checker`
- `protocol_schema_validator`
- `preregistration_consistency_checker`
- `intervention_protocol_linter`
- `quality_gate_plan_builder`

Tool 只能生成候选方案和校验报告，不能批准或直接修改正式研究方案。

### 5.4 Data Analysis Agent

Skills:

- `data_readiness_audit`
- `data_processing_planning`
- `statistical_analysis_execution`
- `model_diagnostic_review`
- `result_card_generation`
- `result_interpretation_bounding`

Tools:

- `dataset_catalog_read`
- `dataset_schema_profile`
- `data_quality_audit`
- `missingness_and_outlier_report`
- `data_processing_executor`
- `python_analysis_sandbox`
- `spss_analysis_adapter`
- `model_diagnostic_runner`
- `statistical_result_card_builder`
- `result_validation_checker`
- `data_freeze_request_builder`

Python、SPSS 和数据处理 Tool 使用受限沙箱。结果卡必须经过验证，数据冻结 Tool 只能提出冻结请求。

### 5.5 Paper Writing Agent

Skills:

- `atomic_claim_graph_construction`
- `imrad_outline_generation`
- `evidence_to_claim_mapping`
- `bilingual_manuscript_rendering`
- `citation_and_number_consistency`
- `limitation_and_reproducibility_writing`

Tools:

- `writing_context_resolver`
- `atomic_claim_validator`
- `claim_evidence_mapper`
- `manuscript_outline_validator`
- `manuscript_renderer_zh`
- `manuscript_renderer_en`
- `bilingual_consistency_checker`
- `citation_consistency_checker`
- `numeric_literal_checker`
- `result_strength_checker`
- `limitation_coverage_checker`
- `reproducibility_statement_builder`
- `table_figure_narrative_builder`

中文稿和英文稿必须从同一个 `AtomicClaimGraph` 生成，Tool 不能单独创建新主张。

### 5.6 Independent Review Agent

Skills:

- `citation_review`
- `methodology_review`
- `statistical_claim_review`
- `reproducibility_review`
- `bilingual_manuscript_review`
- `revision_request_routing`

Tools:

- `citation_audit`
- `evidence_reference_audit`
- `method_protocol_alignment_checker`
- `statistical_claim_audit`
- `result_limitation_audit`
- `reproducibility_artifact_audit`
- `bilingual_draft_audit`
- `review_finding_builder`
- `revision_request_builder`
- `review_summary_builder`

审查 Tool 只能生成结构化 Finding、RevisionRequest 和 ReviewReport，不直接修改被审查稿件。

## 6. Execution Modes and Security

### 6.1 Read-only Tool

只能读取当前项目授权数据，可产生临时统计和审计记录，不创建正式工件。

### 6.2 Candidate-output Tool

可以产生结构化候选正文，写入 `ArtifactContentStore` 和 `ArtifactStore`，但不能改变流程、审批或正式数据状态。

### 6.3 Controlled-write Tool

必须有明确 Controller 权限、审批引用、幂等键和审计记录。默认只生成写入请求，真正写入需要 Controller 的受控执行路径。

### 6.4 Python Sandbox

- 独立子进程或容器。
- 禁止网络访问。
- 只读挂载项目授权数据目录。
- 限制 CPU、内存、磁盘和运行时长。
- 禁止读取环境变量中的 API Key。
- 只允许结构化 JSON、表格或白名单文件输出。
- 禁止任意系统命令、依赖安装和源代码修改。

## 7. Tool Run States and Failure Rules

```text
PENDING -> RUNNING -> SUCCEEDED
                   -> BLOCKED
                   -> FAILED
                   -> TIMED_OUT
                   -> CANCELLED
```

- `SUCCEEDED`：输出通过 Schema、哈希、引用和项目隔离检查。
- `BLOCKED`：权限、审批、网络策略或实现不可用。
- `FAILED`：输入或工具内部错误。
- `TIMED_OUT`：超过工具执行时限。
- `CANCELLED`：Controller 主动取消或项目不再可执行。

失败时不得降级到模型记忆或未经核验数据。证据失败产生证据不足风险；结果校验失败禁止生成可用结果卡；双语失败将稿件标记为 `BLOCKED`。所有失败保留运行记录和风险标记。

## 8. Code Boundaries

建议新增：

```text
backend/src/stem_sci/skills/
  models.py
  registry.py
  resolver.py
  validators.py

backend/src/stem_sci/tools/
  models.py
  registry.py
  gateway.py
  executor.py
  policies.py
  builtin/
    context.py
    artifacts.py
    evidence.py
    research_design.py
    analysis.py
    writing.py
    review.py
  sandbox/
    python_runner.py
```

现有 `operators/` 保留为底层执行实现；`tools/` 面向 Agent 提供能力契约和权限；`skills/` 管理推理流程、Prompt、校验器和 Tool 组合；Controller 只负责治理和路由。

## 9. Implementation Phases

### P0: Shared Foundation

- `ToolSpec`、`ToolResult`、`ToolRunRecord`、`ToolRegistry`。
- `SkillManifest`、`SkillRegistry`、Agent 绑定解析。
- 项目隔离、权限、版本、预算、超时和幂等校验。
- 本地上下文、工件、证据引用、数据目录和审计 Tool。
- Python 沙箱安全约束和失败状态。

### P1: Agent Workflows

- 综述：知识库检索、PaperCard、证据矩阵和冲突分析。
- 研究设计：问题、估计量、DAG、采样、测量和方案校验。
- 数据分析：数据审计、处理、诊断、结果卡和解释边界。
- 写作：上下文解析、主张校验、双语一致性、复现和图表叙事。
- 独立审查：引用、方法、统计、复现和双语审查。

### P2: External and Advanced Providers

- SPSS 适配器。
- 外部文献 Provider 和 Crossref/DOI 查询。
- 远程容器执行。
- 高级因果推断、功效分析和文档导出。

## 10. Acceptance Criteria

- 未授权 Skill/Tool、跨项目引用和未批准写入都会被 Gateway 拒绝。
- Tool 运行和失败状态可按项目审计查询。
- 六个 Agent 均拥有明确、版本化的 Skill 与 Tool 绑定。
- Python 和其他高风险执行均在受限沙箱内完成。
- 综述事实、结果卡、论文主张和审查发现都能回指项目工件。
- Agent 无法直接推进阶段、批准工件、冻结数据、修改正式结果或发布内容。
- 所有 CI 使用 Fake Tool/Fake GPT；外部服务只作为显式本地配置的 Smoke Test。
- API Key、Prompt 正文和原始敏感响应不进入 Git、普通日志或工件正文。
