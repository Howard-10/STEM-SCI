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
