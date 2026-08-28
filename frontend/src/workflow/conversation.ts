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
    add("检索状态", body.retrieval_status); add("检索问题", body.query); add("风险提示", body.risk_flags);
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
