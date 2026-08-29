export type WorkflowConversationItem = WorkflowRouteItem | WorkflowReportItem;

type WorkflowRouteItem = {
  kind: "workflow-route";
  currentAgent: string | null;
  steps: Array<{ agentId: string; name: string; task: string }>;
};

type WorkflowReportItem = {
  kind: "workflow-report";
  agentId: string;
  agentName: string;
  pendingApproval: boolean;
  isLatest: boolean;
  approvalReason: string | null;
  artifacts: Array<{ artifactType: string; body: Record<string, unknown> }>;
};

type TimelineInput = {
  project_id?: string;
  research_intent?: string;
  workflow_state?: { pending_approval_ref?: string | null };
  pending_approval?: { approval_type?: string; reason?: string } | null;
  agent_runs: Array<{ agent_run_id: string; agent_id: string; started_at: string; output_artifact_refs: string[] }>;
  artifact_contents: Array<{ artifact_id: string; artifact_type: string; body: Record<string, unknown> }>;
  artifacts?: Array<{ artifact_id: string; artifact_type: string; content_uri: string; version: number }>;
  routes?: unknown[];
  feedback?: unknown[];
};

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function section(label: string, values: string[]): string {
  return values.length ? `\n${label}：\n${values.map((value) => `- ${value}`).join("\n")}` : "";
}

function valueText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join("、");
  return "";
}

export const artifactLabels: Record<string, string> = {
  AgentReasoningCandidate: "Agent 推理摘要",
  ResearchContractCandidate: "研究契约（候选）",
  ResearchScopeCandidate: "研究边界（候选）",
  ResearchQuestionTree: "研究问题树",
  FeasibilityReport: "可行性报告（候选）",
  ProjectRoadmap: "项目路线图",
  LiteratureRequirementList: "文献证据要求",
  InitialRiskProfile: "初始风险与缓解措施",
  UnresolvedQuestionList: "待确认事项",
  PlanningRationaleCandidate: "规划推理说明",
  EvidenceSet: "证据检索摘要",
  VerifiedEvidenceRef: "证据核验状态",
  EvidenceSufficiencyReport: "证据充分性",
  PaperCardCollection: "候选文献",
  ScreenedPaperSet: "文献初筛",
  EvidenceMatrixCandidate: "证据矩阵",
  ResearchGapReport: "研究空白",
  BoundedEvidenceSynthesis: "限定范围内的证据综合",
  DataAuditSpecification: "数据审查规范",
  AnalysisReadinessReport: "分析准备状态",
  DataProcessingPlanCandidate: "数据处理方案",
  ExecutableAnalysisPlanCandidate: "可执行分析计划",
  CodeSpecificationDraft: "代码规格",
  ModelDiagnosticRecommendation: "模型诊断建议",
  RobustnessCheckPlan: "稳健性检查",
  RiskFlags: "风险提示",
  ManuscriptOutline: "论文大纲",
  ManuscriptDraftZh: "中文论文草稿",
  ManuscriptDraftEn: "英文论文草稿",
  BilingualConsistencyReport: "中英文一致性",
  WritingSufficiencyReport: "写作充分性",
  AtomicClaimGraph: "原子主张与证据映射",
  ClaimEvidenceMap: "主张证据映射",
  ReproducibilityStatement: "可复现性声明",
  ReviewFinding: "独立审查发现",
  RevisionRequest: "修改请求",
  ReviewReport: "独立审查报告",
  ReproducibilityReviewReport: "可复现性审查报告",
};

export function getPlanningClarificationStatus(
  artifacts: Array<{ artifactType: string; body: Record<string, unknown> }>,
): { complete: boolean; missing: string[] } {
  const contract = artifacts.find((artifact) => artifact.artifactType === "ResearchContractCandidate")?.body ?? {};
  const fields: Array<[string, unknown]> = [
    ["研究对象", contract.population],
    ["研究场景", contract.context],
    ["干预与对照", `${valueText(contract.intervention)} ${valueText(contract.comparator)}`],
    ["主要指标", contract.outcomes],
  ];
  const missing = fields
    .filter(([, value]) => {
      const text = valueText(value);
      return !text || text.includes("待确认") || text.includes("研究意图中描述");
    })
    .map(([label]) => label);
  return { complete: missing.length === 0, missing };
}

export type PlanningClarificationAnswers = {
  population: string;
  context: string;
  intervention: string;
  comparator: string;
  outcome: string;
};

export type EvidenceClarificationAnswers = {
  goal: string;
  timeRange: string;
  sources: string;
  preferences: string;
  outputs?: string;
};

export type DesignClarificationAnswers = {
  designType: string;
  samplePlan: string;
  timepoints: string;
  analysisModel: string;
  ethics: string;
};

export type DataAnalysisClarificationAnswers = {
  variables: string;
  missingData: string;
  mode: string;
  privacy: string;
};

export type WritingClarificationAnswers = {
  scope: string;
  languages: string;
  format: string;
  boundary: string;
};

export type ReviewClarificationAnswers = {
  scope: string;
  focus: string;
  threshold: string;
};

export function reviewClarificationsComplete(answers: ReviewClarificationAnswers): boolean {
  return Object.values(answers).every((value) => value.trim().length > 0);
}

export function formatReviewClarificationFeedback(answers: ReviewClarificationAnswers): string {
  return [
    `审查范围：${answers.scope.trim()}`,
    `审查重点：${answers.focus.trim()}`,
    `发布门槛：${answers.threshold.trim()}`,
  ].join("；");
}

export function writingClarificationsComplete(answers: WritingClarificationAnswers): boolean {
  return Object.values(answers).every((value) => value.trim().length > 0);
}

export function formatWritingClarificationFeedback(answers: WritingClarificationAnswers): string {
  return [
    `写作范围：${answers.scope.trim()}`,
    `语言版本：${answers.languages.trim()}`,
    `目标格式：${answers.format.trim()}`,
    `主张边界：${answers.boundary.trim()}`,
  ].join("；");
}

export function dataAnalysisClarificationsComplete(answers: DataAnalysisClarificationAnswers): boolean {
  return Object.values(answers).every((value) => value.trim().length > 0);
}

export function formatDataAnalysisClarificationFeedback(answers: DataAnalysisClarificationAnswers): string {
  return [
    `必需变量：${answers.variables.trim()}`,
    `缺失值处理：${answers.missingData.trim()}`,
    `分析模式：${answers.mode.trim()}`,
    `隐私规则：${answers.privacy.trim()}`,
  ].join("；");
}

export function getDataAnalysisClarificationStatus(
  artifacts: Array<{ artifactType: string; body: Record<string, unknown> }>,
): { complete: boolean; missing: string[] } {
  const packageArtifact = artifacts.find((artifact) => artifact.artifactType === "DataAnalysisPreAnalysisPackage");
  if (packageArtifact) return { complete: true, missing: [] };
  const audit = artifacts.find((artifact) => artifact.artifactType === "DataAuditSpecification")?.body ?? {};
  const missing: string[] = [];
  if (!Array.isArray(audit.required_variables) || audit.required_variables.length === 0) missing.push("必需变量");
  if (!Array.isArray(audit.missingness_checks) || audit.missingness_checks.length === 0) missing.push("缺失值规则");
  if (!Array.isArray(audit.privacy_checks) || audit.privacy_checks.length === 0) missing.push("隐私规则");
  if (!artifacts.some((artifact) => artifact.artifactType === "ExecutableAnalysisPlanCandidate")) missing.push("分析模式");
  return { complete: missing.length === 0, missing };
}

export function designClarificationsComplete(answers: DesignClarificationAnswers): boolean {
  return Object.values(answers).every((value) => value.trim().length > 0);
}

export function formatDesignClarificationFeedback(answers: DesignClarificationAnswers): string {
  return [
    `研究设计：${answers.designType.trim()}`,
    `样本与招募：${answers.samplePlan.trim()}`,
    `测量时间点：${answers.timepoints.trim()}`,
    `统计模型：${answers.analysisModel.trim()}`,
    `伦理与排除规则：${answers.ethics.trim()}`,
  ].join("；");
}

export function evidenceClarificationsComplete(answers: EvidenceClarificationAnswers): boolean {
  return [answers.goal, answers.timeRange, answers.sources].every((value) => value.trim().length > 0);
}

export function workflowProjectIdValid(projectId: string): boolean {
  return projectId.trim().length > 0;
}

export function formatEvidenceClarificationFeedback(answers: EvidenceClarificationAnswers): string {
  const lines = [
    `检索目标：${answers.goal.trim()}`,
    `文献范围：${answers.timeRange.trim()}`,
    `证据来源：${answers.sources.trim()}`,
  ];
  if (answers.preferences.trim()) lines.push(`筛选偏好：${answers.preferences.trim()}`);
  if (answers.outputs?.trim()) lines.push(`期望产出：${answers.outputs.trim()}`);
  return lines.join("；");
}

export function planningClarificationsComplete(answers: PlanningClarificationAnswers): boolean {
  return Object.values(answers).every((value) => value.trim().length > 0);
}

export function isPlanningClarification(question: string): boolean {
  const text = question.trim();
  if (/(?:研究对象|研究人群|研究场景|应用场景|干预与对照|主要指标|结果指标)\s*[:：]/u.test(text)) return true;
  return text.length >= 8
    && !/[?？]$/u.test(text)
    && /(?:我想|希望|面向|针对|采用|比较|关注|研究的是|课程|实验课|课堂场景)/u.test(text);
}

export function formatWorkflowArtifact(artifactType: string, body: Record<string, unknown>): string {
  const lines: string[] = [];
  const add = (label: string, value: unknown) => {
    if (Array.isArray(value)) {
      const values = value.map(valueText).filter(Boolean);
      if (values.length) lines.push(`${label}：\n${values.map((item, index) => `${index + 1}. ${item}`).join("\n")}`);
      return;
    }
    const text = valueText(value);
    if (text) lines.push(`${label}：${text}`);
  };
  if (artifactType === "ResearchScopeCandidate") {
    add("纳入范围", body.in_scope); add("排除范围", body.out_of_scope);
  } else if (artifactType === "ResearchQuestionTree") {
    add("核心研究问题", body.primary_question); add("次级问题", body.secondary_questions); add("不纳入问题", body.out_of_scope_questions);
  } else if (artifactType === "FeasibilityReport") {
    add("可行性状态", body.status); add("可行性假设", body.assumptions); add("约束", body.constraints); add("风险", body.risks); add("待确认事项", body.required_confirmations);
  } else if (artifactType === "ProjectRoadmap") {
    add("后续里程碑", body.milestones); add("人工决策点", body.human_decision_points);
  } else if (artifactType === "ResearchContractCandidate") {
    add("研究主题", body.topic); add("研究人群", body.population); add("研究场景", body.context); add("干预或方法", body.intervention); add("对照条件", body.comparator); add("结果指标", body.outcomes);
  } else if (artifactType === "LiteratureRequirementList") {
    add("所需证据类别", body.required_evidence_categories); add("筛选问题", body.screening_questions);
  } else if (artifactType === "InitialRiskProfile") {
    add("主要风险", body.risks); add("缓解措施", body.mitigations);
  } else if (artifactType === "UnresolvedQuestionList") {
    add("待解决问题", body.items);
  } else if (artifactType === "EvidenceSet") {
    const riskFlags = asList(body.risk_flags);
    add("检索状态", body.retrieval_status);
    if (body.query) lines.push("检索任务：已根据当前研究问题生成检索方案。");
    if (riskFlags.some((flag) => /asset_missing|locator|graph_only|unverified|source_review/i.test(flag))) {
      lines.push("资源提示：当前仅支持探索性检索，正式结论仍需核验论文原文。");
    }
  } else if (artifactType === "CorpusCoverageReport") {
    lines.push(`已找到 ${valueText(body.source_count) || "0"} 个来源、${valueText(body.evidence_count) || "0"} 条证据。`);
    add("已覆盖主题", body.covered_topics);
    add("待补充主题", body.missing_topics);
  } else if (artifactType === "SearchProtocolCandidate") {
    lines.push("已生成限定范围的文献检索方案，等待证据来源挂载后执行。");
  } else if (artifactType === "InclusionExclusionCriteria") {
    add("纳入标准", body.include);
    add("排除标准", body.exclude);
  } else if (artifactType === "LiteratureNeedUpdate") {
    lines.push("文献综合：等待模型完成跨来源比较。");
  } else if (artifactType === "PaperCard") {
    const cards = Array.isArray(body.cards) ? body.cards : [body];
    const validCards = cards.filter((card) => card && typeof card === "object") as Array<Record<string, unknown>>;
    lines.push(`已整理 ${validCards.length} 篇文献卡片。`);
    validCards.slice(0, 5).forEach((card, index) => {
      const title = valueText(card.title) || `文献 ${index + 1}`;
      lines.push(`${index + 1}. ${title}`);
      const findings = Array.isArray(card.main_findings) ? card.main_findings.map(valueText).filter(Boolean) : [];
      if (findings.length) lines.push(`主要发现：${findings.slice(0, 2).join("；")}`);
    });
    if (validCards.length > 5) lines.push(`其余 ${validCards.length - 5} 篇可在证据矩阵中查看。`);
  } else if (artifactType === "EvidenceMatrixCandidate") {
    const rows = Array.isArray(body.rows) ? body.rows : [];
    lines.push(`已形成 ${rows.length} 条证据矩阵记录。`);
  } else if (artifactType === "EvidenceConflictMap") {
    const conflicts = Array.isArray(body.conflicts) ? body.conflicts : [];
    lines.push(conflicts.length ? `发现 ${conflicts.length} 处文献结论差异，需结合原文核验。` : "当前未发现明确的文献结论冲突。");
  } else if (artifactType === "BoundedEvidenceSynthesis") {
    add("限定范围内的综合", body.summary);
    add("适用边界", body.corpus_limit);
  } else if (artifactType === "ResearchQuestionCandidate") {
    add("研究对象", body.population); add("研究场景", body.context); add("干预", body.intervention); add("对照", body.comparator); add("主要指标", body.outcome);
  } else if (artifactType === "HypothesisCandidate") {
    add("候选假设", body.text); add("主要指标", body.outcome);
  } else if (artifactType === "Estimand") {
    add("估计目标", body.summary_measure); add("干预", body.treatment); add("对照", body.comparator); add("结果", body.outcome); add("时间点", body.time);
  } else if (artifactType === "CausalDAG") {
    add("因果图节点", body.required_nodes); add("说明", body.warning);
  } else if (artifactType === "StudyProtocolCandidate") {
    add("设计类型", body.design_type); add("分配方案", body.allocation_description); add("主要指标", body.primary_outcome); add("测量时间点", body.measurement_timepoints); lines.push("该研究方案仍需人工审批，批准前不得收集数据。");
  } else if (artifactType === "SamplingPlan") {
    add("抽样方式", body.approach); add("研究人群", body.population); lines.push("样本可获得性需要在实施前由研究者确认。");
  } else if (artifactType === "InterventionProtocol") {
    add("干预", body.intervention); add("对照", body.comparator); add("分配", body.allocation);
  } else if (artifactType === "MeasurementPlan") {
    add("主要指标", body.primary_outcome); add("次要指标", body.secondary_outcomes); add("测量时间点", body.measurement_timepoints); add("数据字段", body.data_dictionary_fields);
  } else if (artifactType === "PreregisteredAnalysisPlanDraft") {
    add("主要结果", body.primary_outcomes); add("确认性模型", body.confirmatory_models); add("协变量", body.covariates); add("缺失值处理", body.missing_data_strategy); add("异常值处理", body.outlier_strategy); lines.push("这是预注册分析计划候选稿，收集数据前必须完成审批。");
  } else if (artifactType === "QualityGatePlan") {
    add("必经 Gate", body.required_gates); lines.push("质量 Gate 由 Controller 和人工审批共同执行。");
  } else if (artifactType === "DesignRationaleCandidate") {
    add("设计依据", body.estimand_rationale); add("分配风险", body.allocation_risk_notes); add("测量问题", body.measurement_validity_questions); add("分析边界", body.analysis_boundary_notes); add("预注册风险", body.preregistration_risks);
  } else if (artifactType === "DataAuditSpecification") {
    add("必需变量", body.required_variables); add("缺失值检查", body.missingness_checks); add("类型与范围检查", body.range_and_type_checks); add("隐私检查", body.privacy_checks);
  } else if (artifactType === "AnalysisReadinessReport") {
    add("分析准备状态", body.status); add("说明", body.rationale); add("缺失要求", body.missing_requirements);
  } else if (artifactType === "DataProcessingPlanCandidate") {
    add("处理步骤", body.proposed_steps); add("缺失值策略", body.missing_data_strategy_ref); add("排除规则", body.exclusion_rule_refs); lines.push("数据处理方案需要人工确认后才能执行。");
  } else if (artifactType === "ExecutableAnalysisPlanCandidate") {
    add("分析模式", body.analysis_mode); add("模型规格", body.model_specification_refs); add("变量映射", body.variable_mapping); lines.push("执行计划只能作用于通过审查并冻结的数据集。");
  } else if (artifactType === "CodeSpecificationDraft") {
    add("预期语言", body.expected_languages); add("所需输出", body.required_outputs); lines.push("代码仅作为候选规格，执行前需要代码审查和人工确认。");
  } else if (artifactType === "ModelDiagnosticRecommendation") {
    add("诊断检查", body.diagnostic_checks); add("解释边界", body.interpretation_limitations);
  } else if (artifactType === "RobustnessCheckPlan") {
    add("稳健性检查", body.planned_checks); add("报告规则", body.reporting_rule);
  } else if (artifactType === "RiskFlags") {
    add("风险提示", body.items);
  } else if (artifactType === "ManuscriptOutline") {
    add("论文标题", body.title);
    const sections = body.section_claim_ids && typeof body.section_claim_ids === "object" ? Object.keys(body.section_claim_ids as object) : [];
    if (sections.length) lines.push(`已规划章节：${sections.join("、")}`);
  } else if (artifactType === "ManuscriptDraftZh" || artifactType === "ManuscriptDraftEn") {
    const language = artifactType === "ManuscriptDraftZh" ? "中文" : "英文";
    lines.push(`${language}稿状态：${valueText(body.status) || "候选稿"}`);
    const sections = body.sections && typeof body.sections === "object" ? body.sections as Record<string, unknown> : {};
    Object.entries(sections).forEach(([sectionName, content]) => {
      const text = valueText(content);
      if (text) lines.push(`${sectionName}：\n${text}`);
    });
  } else if (artifactType === "BilingualConsistencyReport") {
    add("一致性状态", body.status); add("检查发现", body.findings); add("风险提示", body.risk_flags);
  } else if (artifactType === "WritingSufficiencyReport") {
    add("写作充分性", body.status); add("待补要求", body.missing_requirements);
  } else if (artifactType === "AtomicClaimGraph") {
    const nodes = Array.isArray(body.nodes) ? body.nodes : [];
    lines.push(`已建立 ${nodes.length} 条原子主张及其证据映射。`);
  } else if (artifactType === "ClaimEvidenceMap") {
    add("映射状态", body.status); add("说明", body.reason);
  } else if (artifactType === "ReproducibilityStatement") {
    add("可复现性声明", body.statement);
  } else if (artifactType === "ReviewFinding") {
    add("严重程度", body.severity);
    add("审查类别", body.category);
    add("问题描述", body.description);
    add("建议动作", body.suggested_action);
    add("证据引用", body.evidence_refs);
  } else if (artifactType === "RevisionRequest") {
    add("必须修改内容", body.required_changes);
    add("是否阻塞", body.blocking === true ? "是" : "否");
    add("触发问题", body.triggered_by_refs);
  } else if (artifactType === "ReviewReport") {
    add("总体建议", body.overall_recommendation);
    add("问题数量", Array.isArray(body.finding_refs) ? body.finding_refs.length : 0);
    add("修改请求数量", Array.isArray(body.revision_request_refs) ? body.revision_request_refs.length : 0);
  } else if (artifactType === "ReproducibilityReviewReport") {
    const report = body.report && typeof body.report === "object" ? body.report as Record<string, unknown> : body;
    add("审查结果", report.overall_recommendation);
    add("发现的问题", body.findings);
    add("修改请求", body.revision_requests);
  } else if (artifactType === "VerifiedEvidenceRef") {
    lines.push(body.verified === true ? "证据核验状态：已核验" : "证据核验状态：待人工核验");
    const riskFlags = asList(body.risk_flags);
    if (riskFlags.length || body.verified !== true) lines.push("当前仅支持探索性检索，正式结论仍需核验论文原文。");
  } else if (artifactType === "EvidenceSufficiencyReport") {
    add("证据包状态", body.status);
    add("已纳入证据", body.evidence_count);
    const missing = asList(body.missing_requirements);
    if (missing.length) lines.push(`下一步：${missing.map((item) => item.replaceAll("_", " ")).join("、")}`);
  } else if (artifactType === "PaperCardCollection") {
    const cards = Array.isArray(body.cards) ? body.cards : [];
    lines.push(`已整理 ${cards.length} 篇候选文献。`);
    cards.slice(0, 5).forEach((card, index) => {
      if (card && typeof card === "object" && "title" in card) lines.push(`${index + 1}. ${valueText((card as Record<string, unknown>).title)}`);
    });
    if (cards.length > 5) lines.push(`其余 ${cards.length - 5} 篇可在证据矩阵中查看。`);
  } else if (artifactType === "ScreenedPaperSet") {
    const sources = Array.isArray(body.source_refs) ? body.source_refs : [];
    const evidence = Array.isArray(body.evidence_refs) ? body.evidence_refs : [];
    lines.push(`已完成初筛，涉及 ${sources.length} 个来源、${evidence.length} 条证据。`);
  } else if (artifactType === "AgentReasoningCandidate") {
    add("推理摘要", body.summary); add("关键判断", body.key_decisions); add("待确认问题", body.open_questions); add("风险提示", body.risk_flags);
  } else {
    Object.entries(body).forEach(([key, value]) => add(key, value));
  }
  return lines.join("\n");
}

export function formatMentorPlanningReport(
  artifacts: Array<{ artifactType: string; body: Record<string, unknown> }>,
): string {
  const get = (type: string) => artifacts.find((artifact) => artifact.artifactType === type)?.body ?? {};
  const contract = get("ResearchContractCandidate");
  const questions = get("ResearchQuestionTree");
  const feasibility = get("FeasibilityReport");
  const lines = ["已根据你的研究思路形成初步方案。"];
  if (typeof contract.topic === "string") lines.push(`当前研究主题：${contract.topic}`);
  if (typeof questions.primary_question === "string") lines.push(`核心问题：${questions.primary_question}`);
  lines.push("\n为了继续研究设计，请补充或确认：");
  const clarify = [
    ["研究对象", contract.population, "具体面向哪类学生、教师或研究参与者？"],
    ["研究场景", contract.context, "具体在哪个课程、实验或应用场景中开展？"],
    ["干预与对照", contract.intervention, "准备比较什么方法与基线条件？"],
    ["主要指标", contract.outcomes, "用什么可观测指标判断效果？"],
  ] as const;
  clarify.forEach(([label, current, question]) => {
    const currentText = valueText(current);
    const unresolved = !currentText || currentText.includes("待确认") || currentText.includes("研究意图中描述");
    lines.push(`${label}：${unresolved ? question : currentText}`);
  });
  const confirmations = Array.isArray(feasibility.required_confirmations) ? feasibility.required_confirmations : [];
  if (confirmations.length) lines.push(`\n另外请确认：${confirmations.map(valueText).join("；")}`);
  lines.push("\n你可以直接按“研究对象/场景/干预与对照/主要指标”逐项回复，我会据此更新导师规划。");
  return lines.join("\n");
}

/** Answer follow-up questions from persisted Agent outputs without triggering generic retrieval. */
export function answerWorkflowQuestion(question: string, timeline: TimelineInput): string | null {
  const normalized = question.trim();
  if (!normalized || !/(导师规划|研究边界|问题树|可行性|路线图|规划方案|当前方案)/u.test(normalized)) return null;
  const runs = Array.isArray(timeline.agent_runs) ? timeline.agent_runs : [];
  const latestMentor = [...runs].reverse().find((run) => run.agent_id === "mentor_planning");
  if (!latestMentor) return null;
  const contents = (Array.isArray(timeline.artifact_contents) ? timeline.artifact_contents : []).filter((artifact) => {
    if (artifact.artifact_id.startsWith(`${latestMentor.agent_run_id}:`)) return true;
    const refs = Array.isArray(latestMentor.output_artifact_refs) ? latestMentor.output_artifact_refs : [];
    return refs.some((ref) => ref.includes(`/${artifact.artifact_id}/`) || ref.endsWith(`/${artifact.artifact_id}`));
  });
  if (!contents.length) return "导师规划已运行，但当前时间线还没有挂载可读取的阶段产物。请刷新项目后重试，或退回当前 Agent 要求重新生成。";
  const byType = (type: string) => contents.find((item) => item.artifact_type === type)?.body ?? {};
  const scope = byType("ResearchScopeCandidate");
  const questions = byType("ResearchQuestionTree");
  const feasibility = byType("FeasibilityReport");
  const roadmap = byType("ProjectRoadmap");
  const lines = ["这是当前导师规划 Agent 生成的候选方案解读（仍需你审核，不代表已获得伦理或实证结论）。"];
  if (/研究边界|规划方案|当前方案/u.test(normalized)) {
    lines.push(section("研究边界（候选）", asList(scope.in_scope)));
    lines.push(section("明确排除", asList(scope.out_of_scope)));
  }
  if (/问题树|研究问题|规划方案|当前方案/u.test(normalized)) {
    if (typeof questions.primary_question === "string") lines.push(`\n核心研究问题：${questions.primary_question}`);
    lines.push(section("次级问题", asList(questions.secondary_questions)));
    lines.push(section("不纳入问题", asList(questions.out_of_scope_questions)));
  }
  if (/可行性|规划方案|当前方案/u.test(normalized)) {
    if (typeof feasibility.status === "string") lines.push(`\n可行性状态：${feasibility.status}`);
    lines.push(section("可行性假设", asList(feasibility.assumptions)));
    lines.push(section("约束", asList(feasibility.constraints)));
    lines.push(section("风险", asList(feasibility.risks)));
    lines.push(section("待你确认", asList(feasibility.required_confirmations)));
  }
  if (/路线图|规划方案|当前方案/u.test(normalized)) lines.push(section("后续里程碑", asList(roadmap.milestones)));
  return lines.join("").trim();
}

const steps = [
  { agentId: "mentor_planning", name: "导师规划", task: "研究边界、问题树与可行性方案" },
  { agentId: "evidence_review", name: "证据审查", task: "文献检索、核验与证据矩阵" },
  { agentId: "research_design", name: "研究设计", task: "变量、样本、方法与预注册方案" },
  { agentId: "data_analysis", name: "数据分析", task: "数据要求、分析计划与结果检查" },
  { agentId: "paper_writing", name: "论文写作", task: "论文草稿与引用映射" },
  { agentId: "independent_review", name: "独立审查", task: "可复现性、风险与发布建议" },
];

export function buildWorkflowConversation(timeline: TimelineInput): WorkflowConversationItem[] {
  const runs = [...(Array.isArray(timeline.agent_runs) ? timeline.agent_runs : [])]
    .sort((left, right) => left.started_at.localeCompare(right.started_at));
  const latest = runs.at(-1)?.agent_run_id ?? null;
  return [
    { kind: "workflow-route", currentAgent: runs.at(-1)?.agent_id ?? null, steps },
    ...runs.map((run) => ({
      kind: "workflow-report" as const,
      agentId: run.agent_id,
      agentName: steps.find((step) => step.agentId === run.agent_id)?.name ?? run.agent_id,
      pendingApproval: run.agent_run_id === latest && timeline.workflow_state?.pending_approval_ref != null,
      isLatest: run.agent_run_id === latest,
      approvalReason: run.agent_run_id === latest ? timeline.pending_approval?.reason ?? null : null,
      artifacts: (Array.isArray(timeline.artifact_contents) ? timeline.artifact_contents : [])
        .filter((artifact) => {
          if (artifact.artifact_id.startsWith(`${run.agent_run_id}:`)) return true;
          const refs = Array.isArray(run.output_artifact_refs) ? run.output_artifact_refs : [];
          return refs.some((ref) => ref.includes(`/${artifact.artifact_id}/`) || ref.endsWith(`/${artifact.artifact_id}`));
        })
        .map((artifact) => ({ artifactType: artifact.artifact_type, body: artifact.body })),
    })),
  ];
}

export function findLatestWorkflowReport(
  timeline: TimelineInput,
  agentId: string,
): Extract<WorkflowConversationItem, { kind: "workflow-report" }> | null {
  const reports = buildWorkflowConversation(timeline).filter(
    (item): item is Extract<WorkflowConversationItem, { kind: "workflow-report" }> =>
      item.kind === "workflow-report" && item.agentId === agentId,
  );
  return reports.at(-1) ?? null;
}
