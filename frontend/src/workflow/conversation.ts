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
  workflow_state: { pending_approval_ref: string | null };
  pending_approval?: { approval_type?: string; reason?: string } | null;
  agent_runs: Array<{ agent_run_id: string; agent_id: string; started_at: string; output_artifact_refs: string[] }>;
  artifact_contents: Array<{ artifact_id: string; artifact_type: string; body: Record<string, unknown> }>;
  routes?: unknown[];
  feedback?: unknown[];
};

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
      pendingApproval: run.agent_run_id === latest && timeline.workflow_state.pending_approval_ref !== null,
      isLatest: run.agent_run_id === latest,
      approvalReason: run.agent_run_id === latest ? timeline.pending_approval?.reason ?? null : null,
      artifacts: (Array.isArray(timeline.artifact_contents) ? timeline.artifact_contents : [])
        .filter((artifact) => artifact.artifact_id.startsWith(`${run.agent_run_id}:`))
        .map((artifact) => ({ artifactType: artifact.artifact_type, body: artifact.body })),
    })),
  ];
}
